"""GameRoomRegistry: room membership, session storage, reconnection, room loops, cleanup.

Owns the room id -> GameSession mapping. Builds each GameSession fully wired (its
NetworkPublisher is constructor-injected, never assigned afterward) and starts its
per-room game-loop task; tears a room down once its last connection leaves. It does not
decode wire messages or validate a participant's state - ClientMessageRouter does that
before ever calling in here.
"""

import asyncio
import logging
import secrets
from dataclasses import dataclass

import constants
from protocol.message_types import MessageType
from protocol.snapshot_codec import snapshot_to_payload
from server.game_loop import run_game_loop
from server.interfaces import MessageSender, RatingRepository, Sleeper
from server.participant import ParticipantState
from server.publisher import NetworkPublisher
from server.session import GameSession

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RoomPlacement:
    room_id: str
    session: GameSession
    role: str


def room_placement_payloads(placement):
    role_payload = {"type": MessageType.ROLE.value, "role": placement.role}
    snapshot = placement.session.components.engine.snapshot()
    clock_ms = placement.session.components.engine.clock
    snapshot_payload = snapshot_to_payload(snapshot, clock_ms)
    return role_payload, snapshot_payload


class GameRoomRegistry:
    def __init__(
        self, send_fn: MessageSender, rating_store: RatingRepository,
        tick_ms: int = constants.FRAME_POLL_MS,
        disconnect_countdown_seconds: int = constants.DISCONNECT_COUNTDOWN_SECONDS,
        sleep: Sleeper = asyncio.sleep,
    ):
        self._send_fn = send_fn
        self._rating_store = rating_store
        self._tick_ms = tick_ms
        self._disconnect_countdown_seconds = disconnect_countdown_seconds
        self._sleep = sleep
        self._sessions_by_room_id = {}
        self._connections_by_room_id = {}
        self._game_loop_tasks_by_room_id = {}

    def create_private_room(self, participant):
        room_id, session = self._open_room()
        role = self._place_participant_in_room(room_id, session, participant)
        return RoomPlacement(room_id=room_id, session=session, role=role)

    def join_private_room(self, participant, room_id):
        session = self._sessions_by_room_id.get(room_id)
        if session is None:
            return None
        role = self._place_participant_in_room(room_id, session, participant)
        return RoomPlacement(room_id=room_id, session=session, role=role)

    def create_matched_room(self, white_participant, black_participant):
        room_id, session = self._open_room()

        white_role = self._place_participant_in_room(room_id, session, white_participant)
        black_role = self._place_participant_in_room(room_id, session, black_participant)

        self._send_room_placement(white_participant.connection, RoomPlacement(room_id, session, white_role))
        self._send_room_placement(black_participant.connection, RoomPlacement(room_id, session, black_role))

    def game_session_for(self, participant):
        return self._sessions_by_room_id.get(participant.room_id)

    def try_reconnect(self, participant):
        for room_id, session in self._sessions_by_room_id.items():
            role = session.reconnect(participant.connection, participant.username)
            if role is None:
                continue
            self._connections_by_room_id[room_id].add(participant.connection)
            participant.role = role
            participant.room_id = room_id
            participant.state = ParticipantState.IN_ROOM
            return RoomPlacement(room_id=room_id, session=session, role=role)
        return None

    async def remove_participant(self, participant):
        room_id = participant.room_id
        connections = self._connections_by_room_id.get(room_id)
        if connections is None:
            return False

        connections.discard(participant.connection)
        if connections:
            session = self._sessions_by_room_id.get(room_id)
            if session is not None:
                session.begin_disconnect_countdown(participant.connection)
            return False

        await self._close_room(room_id)
        return True

    def _open_room(self):
        room_id = self._generate_unique_room_id()
        self._connections_by_room_id[room_id] = set()

        session = GameSession(
            constants.STANDARD_START_BOARD,
            make_network_publisher=lambda dispatcher: self._build_network_publisher(room_id, dispatcher),
            rating_store=self._rating_store,
            disconnect_countdown_seconds=self._disconnect_countdown_seconds,
            sleep=self._sleep,
        )
        self._sessions_by_room_id[room_id] = session
        self._game_loop_tasks_by_room_id[room_id] = self._start_game_loop(room_id, session)
        return room_id, session

    def _generate_unique_room_id(self):
        room_id = secrets.token_hex(3)
        while room_id in self._sessions_by_room_id:
            room_id = secrets.token_hex(3)
        return room_id

    def _place_participant_in_room(self, room_id, session, participant):
        role = session.assign_role(participant.connection)
        session.record_login(participant.connection, participant.username)
        self._connections_by_room_id[room_id].add(participant.connection)
        participant.role = role
        participant.room_id = room_id
        participant.state = ParticipantState.IN_ROOM
        return role

    def _send_room_placement(self, connection, placement):
        role_payload, snapshot_payload = room_placement_payloads(placement)
        self._send_fn(connection, role_payload)
        self._send_fn(connection, snapshot_payload)

    def _build_network_publisher(self, room_id, dispatcher):
        def broadcast(payload):
            self._broadcast_to_room(room_id, payload)

        def unicast(connection, payload):
            self._send_fn(connection, payload)

        return NetworkPublisher(dispatcher, broadcast, unicast)

    def _broadcast_to_room(self, room_id, payload):
        for connection in list(self._connections_by_room_id.get(room_id, ())):
            self._send_fn(connection, payload)

    def _broadcast_snapshot(self, room_id, session):
        snapshot = session.components.engine.snapshot()
        clock_ms = session.components.engine.clock
        self._broadcast_to_room(room_id, snapshot_to_payload(snapshot, clock_ms))

    def _start_game_loop(self, room_id, session):
        def broadcast_snapshot():
            self._broadcast_snapshot(room_id, session)

        task = asyncio.create_task(run_game_loop(session, broadcast_snapshot, self._tick_ms))
        task.add_done_callback(lambda finished_task: self._on_game_loop_done(room_id, finished_task))
        return task

    def _on_game_loop_done(self, room_id, task):
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            logger.exception("game loop for room %s failed", room_id)

    async def _close_room(self, room_id):
        task = self._game_loop_tasks_by_room_id.pop(room_id, None)
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._connections_by_room_id.pop(room_id, None)
        self._sessions_by_room_id.pop(room_id, None)
