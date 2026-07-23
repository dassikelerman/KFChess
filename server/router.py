"""ClientMessageRouter: choose which application component handles a typed message.

Dispatches by message type, checks the participant's own state (already in a room?
already authenticated?) before doing anything, and only then delegates straight to a
GameRoomRegistry, a Matchmaker, or a GameSession. Every message here is already a typed
object (MoveIntent, RoomIntent, ...) decoded once by ConnectionLifecycle - this class
never touches a socket, JSON, or a dict.
"""

import logging
from dataclasses import dataclass

from protocol.game_messages import JumpIntent, MoveIntent
from protocol.lobby_messages import Login, PlayIntent, RoomIntent
from protocol.message_types import RoomAction
from server.matchmaker import AlreadyQueuedError, MatchFound
from server.participant import ParticipantState

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
