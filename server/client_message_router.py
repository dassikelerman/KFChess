"""ClientMessageRouter: choose which application component handles a typed message.

Dispatches by exact type(message) through a handler registry built once in __init__ -
one entry per supported message class, mapping straight to the existing private handler
method for it (MoveIntent and JumpIntent share one, since both are in-game actions).
Checks the participant's own state (already in a room? already authenticated?) before
doing anything, then delegates to a GameRoomRegistry, a Matchmaker, or a GameSession.
Every message here is already a typed object decoded once by ConnectionLifecycle - this
class never touches a socket, JSON, or a dict.
"""

import logging
from dataclasses import dataclass

from protocol.game_messages import JumpIntent, MoveIntent
from protocol.lobby_messages import CreateRoomIntent, JoinRoomIntent, Login, PlayIntent
from server.contracts import ParticipantState
from server.matchmaker import AlreadyQueuedError, MatchFound
from server.room_directory import AlreadyInRoomError

logger = logging.getLogger(__name__)


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
        # One entry per supported message class -> its existing handler method. Built
        # once here (not as a class attribute) since each value is a bound method of
        # this instance.
        self._handlers_by_type = {
            Login: self._route_login,
            MoveIntent: self._route_game_action,
            JumpIntent: self._route_game_action,
            PlayIntent: self._route_play_intent,
            CreateRoomIntent: self._route_create_room_intent,
            JoinRoomIntent: self._route_join_room_intent,
        }

    def try_reconnect(self, participant):
        return self._game_room_registry.try_reconnect(participant)

    def route(self, participant, message):
        handler = self._handlers_by_type.get(type(message))
        if handler is None:
            self._reject(participant, f"unrecognized message type {type(message).__name__!r}")
        else:
            return handler(participant, message)

    def _route_login(self, participant, message):
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

    def _route_play_intent(self, participant, message):
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

    def _route_create_room_intent(self, participant, message):
        if participant.state is ParticipantState.IN_ROOM:
            self._reject(participant, "already in a room")
        try:
            return self._game_room_registry.create_private_room(participant)
        except AlreadyInRoomError:
            self._reject(participant, "already in a room")

    def _route_join_room_intent(self, participant, message):
        if participant.state is ParticipantState.IN_ROOM:
            self._reject(participant, "already in a room")
        try:
            return self._route_room_join(participant, message.join_code)
        except AlreadyInRoomError:
            self._reject(participant, "already in a room")

    def _route_room_join(self, participant, join_code):
        placement = self._game_room_registry.join_private_room(participant, join_code)
        if placement is None:
            logger.warning(
                "room join rejected: connection_id=%s username=%s join_code=%s reason=unknown room",
                participant.connection_id, participant.username, join_code,
            )
            return RoomPlacementRejected(reason="unknown room")
        return placement

    def _reject(self, participant, reason):
        logger.warning(
            "rejected message: connection_id=%s username=%s state=%s reason=%s",
            participant.connection_id, participant.username, participant.state.name, reason,
        )
        raise MessageRejected(reason)
