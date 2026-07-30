"""GameRoomRegistry: room membership, session storage, reconnection, ticking, cleanup.

Owns the room id -> GameSession mapping. Builds each GameSession fully wired (its
NetworkPublisher is constructor-injected, never assigned afterward) and tears a room
down once its last connection leaves, or once its game has been over for
ROOM_CLOSE_GRACE_SECONDS - whichever happens first, so a room doesn't sit in memory
forever just because a client never closes its socket after GameOverEvent. Whichever
still-connected participants that leaves behind are reset back to the lobby (state,
room_id, role all cleared) so the same connection can immediately queue or open another
room. It does not decode wire messages or validate a participant's state -
ClientMessageRouter does that before ever calling in here.

tick(dt_ms) advances every active room from the one server loop (see server/ws_server.py)
instead of each room running its own asyncio task - a room failing mid-tick is logged and
skipped, never allowed to take any other room (or the loop itself) down with it.

room_id/username/join_code routing metadata lives in the injected RoomDirectory (Redis)
so a future multi-process deployment can look them up without scanning every process -
see server/room_directory.py. Everything else here (GameSession, connections,
Participants, countdowns) stays exactly what it always was: local, in-process state.
"""

import logging
import secrets
from dataclasses import dataclass

import constants
from protocol.lobby_messages import MatchNotFound, RoleAssigned
from protocol.registry import message_to_payload
from protocol.snapshot_codec import snapshot_to_payload
from server.contracts import MessageSender, ParticipantState, RatingRepository
from server.publisher import NetworkPublisher
from server.room_directory import AlreadyInRoomError, RoomDirectory
from server.session import GameSession

logger = logging.getLogger(__name__)

_ROOM_ID_GENERATION_ATTEMPTS = 5


@dataclass(frozen=True)
class RoomPlacement:
    room_id: str
    session: GameSession
    role: str
    join_code: str | None = None


def build_room_placement_payloads(placement):
    role_payload = message_to_payload(
        RoleAssigned(role=placement.role, room_id=placement.room_id, join_code=placement.join_code),
    )
    snapshot = placement.session.components.engine.snapshot()
    clock_ms = placement.session.components.engine.clock
    snapshot_payload = snapshot_to_payload(snapshot, clock_ms)
    return role_payload, snapshot_payload


class GameRoomRegistry:
    def __init__(
        self, send_fn: MessageSender, rating_store: RatingRepository, directory: RoomDirectory,
        disconnect_countdown_seconds: int = constants.DISCONNECT_COUNTDOWN_SECONDS,
        room_close_grace_seconds: int = constants.ROOM_CLOSE_GRACE_SECONDS,
    ):
        self._send_fn = send_fn
        self._rating_store = rating_store
        self._directory = directory
        self._disconnect_countdown_seconds = disconnect_countdown_seconds
        self._room_close_grace_ms = room_close_grace_seconds * 1000
        self._sessions_by_room_id = {}
        self._connections_by_room_id = {}
        self._participants_by_room_id = {}
        self._usernames_by_room_id = {}
        self._join_codes_by_room_id = {}
        self._closing_after_ms = {}
        self._ms_since_heartbeat = 0
        self._directory.refresh_heartbeat()

    def create_private_room(self, participant):
        room_id, session, join_code = self._reserve_and_build_room(
            [participant.username], with_join_code=True,
        )
        role = self._place_participant_in_room(room_id, session, participant)
        return RoomPlacement(room_id=room_id, session=session, role=role, join_code=join_code)

    def join_private_room(self, participant, join_code):
        room_id = self._directory.reserve_join(join_code, participant.username)
        if room_id is None:
            return None
        session = self._sessions_by_room_id.get(room_id)
        if session is None:
            logger.error(
                "directory resolved join_code=%r to room_id=%r but no local session exists for it",
                join_code, room_id,
            )
            self._directory.release_username(participant.username)
            return None
        role = self._place_participant_in_room(room_id, session, participant)
        return RoomPlacement(room_id=room_id, session=session, role=role)

    def create_matched_room(self, white_participant, black_participant):
        try:
            room_id, session, _ = self._reserve_and_build_room(
                [white_participant.username, black_participant.username],
            )
        except AlreadyInRoomError:
            logger.warning(
                "matched room reservation conflict: white=%r black=%r - one of them is already seated elsewhere",
                white_participant.username, black_participant.username,
            )
            self._reject_stale_match(white_participant)
            self._reject_stale_match(black_participant)
            return

        white_role = self._place_participant_in_room(room_id, session, white_participant)
        black_role = self._place_participant_in_room(room_id, session, black_participant)

        self._send_room_placement(white_participant.connection, RoomPlacement(room_id, session, white_role))
        self._send_room_placement(black_participant.connection, RoomPlacement(room_id, session, black_role))

    def _reject_stale_match(self, participant):
        participant.state = ParticipantState.LOBBY
        self._send_fn(participant.connection, message_to_payload(MatchNotFound(reason="match_conflict")))

    def game_session_for(self, participant):
        return self._sessions_by_room_id.get(participant.room_id)

    def try_reconnect(self, participant):
        for room_id, session in self._sessions_by_room_id.items():
            role = session.reconnect(participant.connection, participant.username)
            if role is None:
                continue
            self._connections_by_room_id[room_id].add(participant.connection)
            self._replace_participant_in_room(room_id, participant)
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
        self._participants_by_room_id.get(room_id, {}).pop(participant.connection, None)
        if connections:
            session = self._sessions_by_room_id.get(room_id)
            if session is not None:
                session.begin_disconnect_countdown(participant.connection)
            return False

        self._close_room(room_id)
        return True

    # -- tick ---------------------------------------------------------------

    def tick(self, dt_ms):
        self._ms_since_heartbeat += dt_ms
        if self._ms_since_heartbeat >= constants.SHARD_HEARTBEAT_REFRESH_SECONDS * 1000:
            self._directory.refresh_heartbeat()
            self._ms_since_heartbeat = 0

        for room_id in list(self._sessions_by_room_id):
            session = self._sessions_by_room_id.get(room_id)
            if session is None:
                continue  # removed by something earlier in this same tick
            self._tick_room(room_id, session, dt_ms)

    def _tick_room(self, room_id, session, dt_ms):
        try:
            session.tick(dt_ms)
            self._broadcast_snapshot(room_id, session)
            self._advance_room_closure(room_id, session, dt_ms)
        except Exception:
            logger.exception("game tick for room %s failed", room_id)

    def _advance_room_closure(self, room_id, session, dt_ms):
        if not session.components.engine.game_over:
            return
        remaining_ms = self._closing_after_ms.get(room_id, self._room_close_grace_ms) - dt_ms
        if remaining_ms <= 0:
            self._close_room(room_id)
        else:
            self._closing_after_ms[room_id] = remaining_ms

    # -- room lifecycle -------------------------------------------------------

    def _reserve_and_build_room(self, usernames, with_join_code=False):
        room_id, join_code = self._reserve_new_room(usernames, with_join_code=with_join_code)
        try:
            session = self._build_local_room(room_id)
        except Exception:
            # The Redis reservation already succeeded - if the local room/session
            # construction blows up, undo it. Otherwise every username here stays
            # falsely marked "in a room" with nothing actually built, locking them
            # out of ever playing again (the same false-positive the reservation
            # script itself is designed to prevent, just from a local failure
            # instead of a Redis-side race).
            self._connections_by_room_id.pop(room_id, None)
            self._participants_by_room_id.pop(room_id, None)
            self._usernames_by_room_id.pop(room_id, None)
            self._sessions_by_room_id.pop(room_id, None)
            self._directory.close_room(room_id, usernames, join_code=join_code)
            raise
        if join_code is not None:
            self._join_codes_by_room_id[room_id] = join_code
        return room_id, session, join_code

    def _build_local_room(self, room_id):
        self._connections_by_room_id[room_id] = set()
        self._participants_by_room_id[room_id] = {}
        self._usernames_by_room_id[room_id] = set()

        session = GameSession(
            constants.STANDARD_START_BOARD,
            make_network_publisher=lambda dispatcher: self._build_network_publisher(room_id, dispatcher),
            rating_store=self._rating_store,
            disconnect_countdown_seconds=self._disconnect_countdown_seconds,
        )
        self._sessions_by_room_id[room_id] = session
        return session

    def _reserve_new_room(self, usernames, with_join_code=False):
        # room_id (128 bits) and join_code (30 bits, drawn fresh per attempt) are each
        # independently collision-resistant enough that this loop almost never spins
        # more than once - it exists for correctness, not because collisions are expected.
        for _ in range(_ROOM_ID_GENERATION_ATTEMPTS):
            room_id = secrets.token_hex(constants.ROOM_ID_BYTES)
            join_code = self._generate_join_code() if with_join_code else None
            status = self._directory.reserve_new_room(room_id, usernames, join_code=join_code)
            if status == "ok":
                return room_id, join_code
            if status == "username_conflict":
                raise AlreadyInRoomError(f"one of {usernames!r} is already seated in a room")
        raise RuntimeError("could not allocate a unique room_id/join_code after several attempts")

    @staticmethod
    def _generate_join_code():
        return "".join(secrets.choice(constants.JOIN_CODE_ALPHABET) for _ in range(constants.JOIN_CODE_LENGTH))

    def _place_participant_in_room(self, room_id, session, participant):
        role = session.assign_role(participant.connection)
        session.record_login(participant.connection, participant.username)
        self._connections_by_room_id[room_id].add(participant.connection)
        self._participants_by_room_id[room_id][participant.connection] = participant
        self._usernames_by_room_id[room_id].add(participant.username)
        participant.role = role
        participant.room_id = room_id
        participant.state = ParticipantState.IN_ROOM
        return role

    def _replace_participant_in_room(self, room_id, participant):
        # A reconnect swaps in a brand-new Participant/connection for the same seat -
        # drop the stale (now-dead) connection's entry so _close_room resets the live one.
        participants = self._participants_by_room_id[room_id]
        stale_connection = next(
            (connection for connection, other in participants.items() if other.username == participant.username),
            None,
        )
        participants.pop(stale_connection, None)
        participants[participant.connection] = participant

    def _send_room_placement(self, connection, placement):
        role_payload, snapshot_payload = build_room_placement_payloads(placement)
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

    def _close_room(self, room_id):
        for participant in self._participants_by_room_id.pop(room_id, {}).values():
            participant.state = ParticipantState.LOBBY
            participant.room_id = None
            participant.role = None
        # Every username ever seated here, not just the ones still connected - a
        # participant who disconnected mid-game was already dropped from
        # _participants_by_room_id above (by remove_participant), but their
        # directory:user:{username} entry still needs clearing or they get a false
        # "already in a room" on their next create/join attempt.
        usernames = self._usernames_by_room_id.pop(room_id, set())
        join_code = self._join_codes_by_room_id.pop(room_id, None)
        self._directory.close_room(room_id, usernames, join_code=join_code)
        self._connections_by_room_id.pop(room_id, None)
        self._sessions_by_room_id.pop(room_id, None)
        self._closing_after_ms.pop(room_id, None)
