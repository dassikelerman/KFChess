"""ConnectionLifecycle + ClientMessageRouter: the incoming-message pipeline, in order.

Together these two classes are the whole receive -> decode -> validate state -> route
story for one connection. ConnectionLifecycle is the only place that touches a raw
`connection` object end to end: register it, authenticate it (the login handshake lives
right here - it has exactly one caller and is simply step one of the story this class
already narrates), try to seat it back into a game it disconnected from, decode each
incoming message exactly once, and translate whatever comes back into the actual
outbound JSON. ClientMessageRouter is what "whatever comes back" means: it checks the
participant's own state (already in a room? already authenticated?) and only then
dispatches to a GameRoomRegistry, a Matchmaker, or a GameSession.

Kept as two classes rather than folded into one - state-checking-and-dispatch is a
distinct responsibility from owning a socket, and each is independently testable without
the other (ClientMessageRouter never touches a socket, JSON, or a dict; every message it
sees has already been decoded once by ConnectionLifecycle).
"""

import asyncio
import json
import logging
from dataclasses import dataclass

import websockets

from protocol.game_messages import JumpIntent, MoveIntent
from protocol.lobby_messages import LoggedIn, Login, PlayIntent, RoomCreated, RoomIntent, RoomRejected
from protocol.message_types import RoomAction
from protocol.registry import decode_json_message, encode_json_message
from server.contracts import Participant, ParticipantState
from server.matchmaker import AlreadyQueuedError, MatchFound
from server.rooms import RoomPlacement, room_placement_payloads

logger = logging.getLogger(__name__)

LOGIN_TIMEOUT_S = 5
REJECTED_LOGIN_CLOSE_CODE = 1008


def _decode_login(raw):
    """Decode a Login off the wire through the same registry as every other message,
    then apply login's own business rules (trimmed, non-empty) on top of the typed
    result - the registry only guarantees shape, not that the fields are meaningful."""
    try:
        message = decode_json_message(raw)
    except Exception:
        return None, None, "expected a Login message"

    if not isinstance(message, Login):
        return None, None, "expected a Login message"
    if not isinstance(message.username, str):
        return None, None, "username must be a string"
    if not isinstance(message.password, str):
        return None, None, "password must be a string"

    username = message.username.strip()
    if not username:
        return None, None, "username must not be empty"
    if not message.password:
        return None, None, "password must not be empty"

    return username, message.password, None


async def await_login(connection, user_store):
    try:
        raw = await asyncio.wait_for(connection.recv(), timeout=LOGIN_TIMEOUT_S)
    except asyncio.TimeoutError:
        await connection.close(code=REJECTED_LOGIN_CLOSE_CODE, reason="login timed out")
        return None
    except websockets.ConnectionClosed:
        return None

    username, password, rejection_reason = _decode_login(raw)
    if rejection_reason is not None:
        await connection.close(code=REJECTED_LOGIN_CLOSE_CODE, reason=rejection_reason)
        return None

    if user_store.create_or_verify(username, password) == "wrong_password":
        await connection.close(code=REJECTED_LOGIN_CLOSE_CODE, reason="wrong password")
        return None

    return username


class MessageRejected(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class RoomPlacementRejected:
    reason: str


class ClientMessageRouter:
    def __init__(self, game_room_registry, matchmaker):
        self._game_room_registry = game_room_registry
        self._matchmaker = matchmaker

    def try_reconnect(self, participant):
        return self._game_room_registry.try_reconnect(participant)

    def route(self, participant, message):
        if isinstance(message, Login):
            return self._route_login(participant)
        if isinstance(message, (MoveIntent, JumpIntent)):
            return self._route_game_action(participant, message)
        if isinstance(message, PlayIntent):
            return self._route_play_intent(participant)
        if isinstance(message, RoomIntent):
            return self._route_room_intent(participant, message)
        self._reject(participant, f"unrecognized message type {type(message).__name__!r}")

    def _route_login(self, participant):
        if participant.authenticated:
            self._reject(participant, "already authenticated")

    def _route_game_action(self, participant, message):
        if participant.state is not ParticipantState.IN_ROOM:
            self._reject(
                participant, f"{type(message).__name__} requires an active room (state={participant.state.name})",
            )
        session = self._game_room_registry.game_session_for(participant)
        if session is None:
            self._reject(participant, "no active game session for this room")

        if isinstance(message, MoveIntent):
            session.handle_move(participant.connection, message)
        else:
            session.handle_jump(participant.connection, message)

    def _route_play_intent(self, participant):
        if participant.state is ParticipantState.IN_ROOM:
            self._reject(participant, "already in a room")
        try:
            result = self._matchmaker.enqueue_or_match(participant)
        except AlreadyQueuedError:
            self._reject(participant, "already queued for a match")
            return

        if isinstance(result, MatchFound):
            self._game_room_registry.create_matched_room(result.white, result.black)
        else:
            participant.state = ParticipantState.SEARCHING

    def _route_room_intent(self, participant, message):
        if participant.state is ParticipantState.IN_ROOM:
            self._reject(participant, "already in a room")
        if message.action is RoomAction.CREATE:
            return self._game_room_registry.create_private_room(participant)
        return self._route_room_join(participant, message.room_id)

    def _route_room_join(self, participant, room_id):
        placement = self._game_room_registry.join_private_room(participant, room_id)
        if placement is None:
            logger.warning(
                "room join rejected: connection_id=%s username=%s room_id=%s reason=unknown room",
                participant.connection_id, participant.username, room_id,
            )
            return RoomPlacementRejected(reason="unknown room")
        return placement

    def _reject(self, participant, reason):
        logger.warning(
            "rejected message: connection_id=%s username=%s state=%s reason=%s",
            participant.connection_id, participant.username, participant.state.name, reason,
        )
        raise MessageRejected(reason)


class ConnectionLifecycle:
    def __init__(self, user_store, rating_store, router, on_disconnect):
        self._user_store = user_store
        self._rating_store = rating_store
        self._router = router
        self._on_disconnect = on_disconnect

    async def run(self, connection) -> None:
        participant = self._register_connection(connection)
        try:
            if not await self._authenticate(participant):
                return
            await self._enter_lobby(participant)
            await self._attempt_reconnect(participant)
            await self._receive_messages(participant)
        finally:
            await self._handle_disconnect(participant)

    def _register_connection(self, connection):
        participant = Participant(connection=connection)
        logger.info("connection opened: connection_id=%s", participant.connection_id)
        return participant

    async def _authenticate(self, participant):
        username = await await_login(participant.connection, self._user_store)
        if username is None:
            logger.warning("login rejected: connection_id=%s", participant.connection_id)
            return False

        participant.username = username
        participant.authenticated = True
        participant.state = ParticipantState.LOBBY
        logger.info("login succeeded: connection_id=%s username=%s", participant.connection_id, username)
        return True

    async def _enter_lobby(self, participant):
        participant.rating = self._rating_store.get_rating(participant.username)
        await self._send_message(participant, LoggedIn(username=participant.username, rating=participant.rating))
        logger.info(
            "entered lobby: connection_id=%s username=%s rating=%s",
            participant.connection_id, participant.username, participant.rating,
        )

    async def _attempt_reconnect(self, participant):
        placement = self._router.try_reconnect(participant)
        if placement is None:
            return
        await self._send_room_placement(participant, placement)
        logger.info(
            "reconnected: connection_id=%s username=%s room_id=%s role=%s",
            participant.connection_id, participant.username, placement.room_id, placement.role,
        )

    async def _receive_messages(self, participant):
        async for raw in participant.connection:
            await self._handle_incoming_message(participant, raw)

    async def _handle_incoming_message(self, participant, raw):
        try:
            message = decode_json_message(raw)
        except Exception:
            logger.warning("malformed or unrecognized message: connection_id=%s", participant.connection_id)
            return

        try:
            result = self._router.route(participant, message)
        except MessageRejected:
            return  # the router already logged the rejection with its reason
        except Exception:
            logger.exception("unexpected failure routing a message: connection_id=%s", participant.connection_id)
            return

        await self._apply_route_result(participant, message, result)

    async def _apply_route_result(self, participant, message, result):
        if isinstance(result, RoomPlacement):
            created = isinstance(message, RoomIntent) and message.action is RoomAction.CREATE
            await self._announce_room_placement(participant, result, created)
        elif isinstance(result, RoomPlacementRejected):
            await self._send_message(participant, RoomRejected(reason=result.reason))

    async def _announce_room_placement(self, participant, placement, created):
        if created:
            await self._send_message(participant, RoomCreated(room_id=placement.room_id))
        await self._send_room_placement(participant, placement)
        logger.info(
            "placed in room: connection_id=%s username=%s room_id=%s role=%s",
            participant.connection_id, participant.username, placement.room_id, placement.role,
        )

    async def _send_room_placement(self, participant, placement):
        role_payload, snapshot_payload = room_placement_payloads(placement)
        await participant.connection.send(json.dumps(role_payload))
        await participant.connection.send(json.dumps(snapshot_payload))

    async def _send_message(self, participant, message):
        await participant.connection.send(encode_json_message(message))

    async def _handle_disconnect(self, participant):
        participant.state = ParticipantState.DISCONNECTED
        logger.info(
            "connection closed: connection_id=%s username=%s", participant.connection_id, participant.username,
        )
        await self._on_disconnect(participant)
