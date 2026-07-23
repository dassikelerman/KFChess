"""ConnectionLifecycle: authentication, receive loop, routing, disconnect cleanup.

The only place that touches a raw `connection` object end to end: register it,
authenticate it (the login handshake lives right here - it has exactly one caller and
is simply step one of the story this class already narrates), try to seat it back into
a game it disconnected from, decode each incoming message exactly once and hand the
typed result to ClientMessageRouter, then translate whatever the router returns into
the actual outbound JSON. Everything the router/GameRoomRegistry/Matchmaker decide is
synchronous and typed, with no socket or JSON in sight; this class is the async adapter
between that world and the real network.
"""

import asyncio
import json
import logging

import websockets

from protocol.lobby_messages import LoggedIn, Login, RoomCreated, RoomIntent, RoomRejected
from protocol.message_types import RoomAction
from protocol.registry import decode_json_message, encode_json_message
from server.participant import Participant, ParticipantState
from server.rooms import RoomPlacement, room_placement_payloads
from server.router import MessageRejected, RoomPlacementRejected

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
