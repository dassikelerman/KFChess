import asyncio

import constants
from events.game_events import GameOverEvent, PlayerDisconnectedEvent
from model.piece import PieceColor
from model.position import Position
from server.contracts import Participant, ParticipantState
from server.rating import RatingStore
from server.room_directory import RoomDirectory
from server.rooms import GameRoomRegistry, RoomPlacement
from server.user_store import UserStore
from tests.db_helpers import reset_users_table
from tests.redis_helpers import flush_directory


class _FakeRatingStore:
    """update_ratings() against a real RatingStore needs the usernames to already exist
    in Postgres - fine for the two tests that specifically exercise that wiring, but
    every other test here just needs GameOverEvent to be handled without touching a
    real database for usernames it never registered."""

    def update_ratings(self, white_username, black_username, winner_color):
        return (0, 0)


def _make_directory(game_server_id="test-shard"):
    flush_directory()
    return RoomDirectory(game_server_id)


def _make_registry(rating_store=None):
    sent = []

    def send_fn(connection, payload):
        sent.append((connection, payload))

    if rating_store is None:
        rating_store = _FakeRatingStore()
    return GameRoomRegistry(send_fn, rating_store, _make_directory()), sent


def _make_participant(label):
    return Participant(connection=f"conn-{label}", username=label)


def test_create_private_room_returns_a_unique_room_id_and_creator_becomes_white():
    async def scenario():
        registry, _ = _make_registry()
        participant = _make_participant("a")

        placement = registry.create_private_room(participant)

        assert isinstance(placement, RoomPlacement)
        assert placement.role == "white"
        assert placement.room_id in registry._sessions_by_room_id
        assert participant.role == "white"
        assert participant.room_id == placement.room_id
        assert participant.state is ParticipantState.IN_ROOM

        await registry.remove_participant(participant)

    asyncio.run(scenario())


def test_create_private_room_also_returns_a_join_code_for_a_friend_to_use():
    async def scenario():
        registry, _ = _make_registry()
        participant = _make_participant("a")

        placement = registry.create_private_room(participant)

        assert placement.join_code
        assert len(placement.join_code) == constants.JOIN_CODE_LENGTH
        assert placement.join_code != placement.room_id

        await registry.remove_participant(participant)

    asyncio.run(scenario())


def test_two_create_private_room_calls_produce_distinct_room_ids():
    async def scenario():
        registry, _ = _make_registry()
        participant_a = _make_participant("a")
        participant_b = _make_participant("b")

        placement_a = registry.create_private_room(participant_a)
        placement_b = registry.create_private_room(participant_b)

        assert placement_a.room_id != placement_b.room_id

        await registry.remove_participant(participant_a)
        await registry.remove_participant(participant_b)

    asyncio.run(scenario())


def test_create_private_room_retries_the_room_id_after_a_directory_collision(monkeypatch):
    async def scenario():
        registry, _ = _make_registry()
        registry._directory.reserve_new_room("aaaa", [])  # pre-occupy "aaaa"
        values = iter(["aaaa", "bbbb"])
        monkeypatch.setattr("server.rooms.secrets.token_hex", lambda n: next(values))

        participant = _make_participant("a")
        placement = registry.create_private_room(participant)

        assert placement.room_id == "bbbb"

        await registry.remove_participant(participant)

    asyncio.run(scenario())


def test_create_private_room_rejects_a_creator_already_seated_elsewhere():
    async def scenario():
        registry, _ = _make_registry()
        participant = Participant(connection="conn-dup", username="alice")
        registry._directory.reserve_new_room("room-elsewhere", ["alice"])

        try:
            registry.create_private_room(participant)
            assert False, "expected AlreadyInRoomError"
        except Exception as error:
            assert type(error).__name__ == "AlreadyInRoomError"

    asyncio.run(scenario())


def test_create_private_room_rolls_back_the_directory_reservation_if_local_construction_fails(monkeypatch):
    # The Redis reservation always happens first. If building the local GameSession
    # then blows up for any reason, the reservation must not survive - otherwise the
    # creator's username stays falsely marked "in a room" forever, with no room to
    # match, and they can never create or join another one on this connection.
    async def scenario():
        registry, _ = _make_registry()
        participant = Participant(connection="conn-a", username="alice")

        def _raise(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr("server.rooms.GameSession", _raise)

        try:
            registry.create_private_room(participant)
            assert False, "expected RuntimeError"
        except RuntimeError:
            pass

        assert registry._directory.get_room_for_username("alice") is None
        assert registry._sessions_by_room_id == {}
        assert registry._connections_by_room_id == {}
        assert registry._participants_by_room_id == {}

    asyncio.run(scenario())


def test_create_matched_room_rolls_back_the_directory_reservation_if_local_construction_fails(monkeypatch):
    async def scenario():
        registry, sent = _make_registry()
        white = Participant(connection="conn-white", username="alice")
        black = Participant(connection="conn-black", username="bob")

        def _raise(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr("server.rooms.GameSession", _raise)

        try:
            registry.create_matched_room(white, black)
            assert False, "expected RuntimeError"
        except RuntimeError:
            pass

        assert registry._directory.get_room_for_username("alice") is None
        assert registry._directory.get_room_for_username("bob") is None
        assert registry._sessions_by_room_id == {}
        # A crash here must not silently notify anyone of a match that never happened.
        assert sent == []

    asyncio.run(scenario())


def test_join_private_room_assigns_black_then_spectator_and_none_for_an_unknown_code():
    async def scenario():
        registry, _ = _make_registry()
        creator = _make_participant("a")
        placement = registry.create_private_room(creator)

        second = _make_participant("b")
        second_placement = registry.join_private_room(second, placement.join_code)
        assert second_placement.role == "black"
        assert second.role == "black"
        assert second.room_id == placement.room_id
        assert second.state is ParticipantState.IN_ROOM

        third = _make_participant("c")
        third_placement = registry.join_private_room(third, placement.join_code)
        assert third_placement.role == "spectator"

        assert registry.join_private_room(_make_participant("d"), "NOSUCH") is None

        await registry.remove_participant(creator)
        await registry.remove_participant(second)
        await registry.remove_participant(third)

    asyncio.run(scenario())


def test_join_private_room_rejects_a_joiner_already_seated_elsewhere():
    async def scenario():
        registry, _ = _make_registry()
        creator = _make_participant("a")
        placement = registry.create_private_room(creator)
        elsewhere_participant = Participant(connection="conn-elsewhere", username="bob")
        registry._directory.reserve_new_room("room-elsewhere", ["bob"])

        try:
            registry.join_private_room(elsewhere_participant, placement.join_code)
            assert False, "expected AlreadyInRoomError"
        except Exception as error:
            assert type(error).__name__ == "AlreadyInRoomError"

        await registry.remove_participant(creator)

    asyncio.run(scenario())


def test_join_private_room_handles_a_directory_entry_with_no_local_session():
    # Defensive branch for the eventual multi-shard world: the Directory resolves a
    # join_code to a room_id this process never actually built locally (it always
    # will in today's single-process step, but the code must not crash if it doesn't).
    async def scenario():
        registry, _ = _make_registry()
        registry._directory.reserve_new_room("orphan-room", [], join_code="ORPHAN1")
        joiner = Participant(connection="conn-joiner", username="joiner")

        result = registry.join_private_room(joiner, "ORPHAN1")

        assert result is None
        assert registry._directory.get_room_for_username("joiner") is None

    asyncio.run(scenario())


def test_two_rooms_have_independent_sessions_and_game_state():
    async def scenario():
        registry, _ = _make_registry()
        participant_a = _make_participant("a")
        participant_b = _make_participant("b")

        placement_a = registry.create_private_room(participant_a)
        placement_b = registry.create_private_room(participant_b)

        assert placement_a.session is not placement_b.session

        engine_a = placement_a.session.components.engine
        engine_b = placement_b.session.components.engine

        result = engine_a.request_move(Position(6, 0), Position(5, 0))
        assert result.is_accepted
        engine_a.wait(constants.MOVE_DURATION + 1)

        assert engine_a.piece_at(Position(5, 0)) is not None
        assert engine_a.piece_at(Position(6, 0)) is None
        assert engine_b.piece_at(Position(5, 0)) is None
        assert engine_b.piece_at(Position(6, 0)) is not None

        await registry.remove_participant(participant_a)
        await registry.remove_participant(participant_b)

    asyncio.run(scenario())


def test_remove_client_on_the_last_connection_removes_the_room():
    async def scenario():
        registry, _ = _make_registry()
        participant = _make_participant("a")
        placement = registry.create_private_room(participant)

        became_empty = await registry.remove_participant(participant)

        assert became_empty is True
        assert placement.room_id not in registry._sessions_by_room_id
        assert placement.room_id not in registry._connections_by_room_id

        registry.tick(16)  # a tick after removal must not raise or resurrect the room
        assert placement.room_id not in registry._sessions_by_room_id

    asyncio.run(scenario())


def test_remove_client_leaves_the_room_intact_when_other_connections_remain():
    async def scenario():
        registry, _ = _make_registry()
        creator = _make_participant("a")
        placement = registry.create_private_room(creator)
        second = _make_participant("b")
        registry.join_private_room(second, placement.join_code)

        became_empty = await registry.remove_participant(creator)

        assert became_empty is False
        assert placement.room_id in registry._sessions_by_room_id

        await registry.remove_participant(second)

    asyncio.run(scenario())


def test_tick_advances_every_active_room_and_broadcasts_one_snapshot_each():
    async def scenario():
        registry, sent = _make_registry()
        participant_a = _make_participant("a")
        participant_b = _make_participant("b")
        placement_a = registry.create_private_room(participant_a)
        placement_b = registry.create_private_room(participant_b)
        clock_a_before = placement_a.session.components.engine.clock
        clock_b_before = placement_b.session.components.engine.clock

        registry.tick(16)

        assert placement_a.session.components.engine.clock == clock_a_before + 16
        assert placement_b.session.components.engine.clock == clock_b_before + 16
        snapshot_payloads = [payload for _, payload in sent if payload["type"] == "GameSnapshot"]
        assert len(snapshot_payloads) == 2  # exactly one per active room, per tick

        await registry.remove_participant(participant_a)
        await registry.remove_participant(participant_b)

    asyncio.run(scenario())


def test_a_room_removed_during_iteration_by_an_earlier_room_does_not_crash_the_tick():
    # Simulates a room disappearing mid-tick (e.g. another room's tick tears it down) -
    # tick() must tolerate a room_id it already snapshotted no longer being present.
    registry, _ = _make_registry()
    participant = _make_participant("a")
    placement = registry.create_private_room(participant)
    del registry._sessions_by_room_id[placement.room_id]

    registry.tick(16)  # must not raise


def test_an_exception_in_one_rooms_tick_is_logged_and_does_not_affect_another_room(caplog):
    async def scenario():
        failing_connection = "conn-fail"

        def send_fn(connection, payload):
            if connection == failing_connection:
                raise RuntimeError("boom")

        registry = GameRoomRegistry(send_fn, _FakeRatingStore(), _make_directory())
        failing_participant = Participant(connection=failing_connection, username="failing")
        healthy_participant = _make_participant("healthy")

        failing_placement = registry.create_private_room(failing_participant)
        healthy_placement = registry.create_private_room(healthy_participant)

        with caplog.at_level("ERROR"):
            registry.tick(16)

        assert "game tick for room" in caplog.text
        # A failing room is logged and skipped, not torn down and not allowed to stop
        # the healthy room's tick from happening.
        assert failing_placement.room_id in registry._sessions_by_room_id
        assert healthy_placement.session.components.engine.clock == 16

        await registry.remove_participant(healthy_participant)
        await registry.remove_participant(failing_participant)

    asyncio.run(scenario())


def test_create_private_room_wires_a_real_rating_store_into_the_sessions_rating_flow():
    async def scenario():
        reset_users_table()
        user_store = UserStore()
        rating_store = RatingStore()
        user_store.create_or_verify("alice", "hunter2")
        user_store.create_or_verify("bob", "hunter2")
        registry, _ = _make_registry(rating_store=rating_store)
        white_participant = Participant(connection="conn-white", username="alice")
        black_participant = Participant(connection="conn-black", username="bob")

        placement = registry.create_private_room(white_participant)
        registry.join_private_room(black_participant, placement.join_code)

        event = GameOverEvent(winner_color=PieceColor.WHITE, at_ms=100)
        placement.session.components.dispatcher.publish(event)

        assert rating_store.get_rating("alice") == 1216
        assert rating_store.get_rating("bob") == 1184

        await registry.remove_participant(white_participant)
        await registry.remove_participant(black_participant)

    asyncio.run(scenario())


def test_disconnect_countdown_params_are_threaded_into_every_session_it_builds():
    async def scenario():
        registry = GameRoomRegistry(
            lambda connection, payload: None, _FakeRatingStore(), _make_directory(), disconnect_countdown_seconds=2,
        )
        white_participant = _make_participant("white")
        black_participant = _make_participant("black")
        placement = registry.create_private_room(white_participant)
        registry.join_private_room(black_participant, placement.join_code)

        events = []
        placement.session.components.dispatcher.subscribe(PlayerDisconnectedEvent, events.append)

        placement.session.begin_disconnect_countdown(white_participant.connection)
        placement.session.tick(1000)
        placement.session.tick(1000)

        assert [e.seconds_remaining for e in events] == [2, 1, 0]
        assert placement.session.components.engine.game_over is True

        await registry.remove_participant(white_participant)
        await registry.remove_participant(black_participant)

    asyncio.run(scenario())


def test_room_closes_itself_a_grace_period_after_the_game_ends():
    async def scenario():
        registry = GameRoomRegistry(
            lambda connection, payload: None, _FakeRatingStore(), _make_directory(), room_close_grace_seconds=1,
        )
        participant = _make_participant("a")
        placement = registry.create_private_room(participant)

        placement.session.components.engine.resign(PieceColor.WHITE)

        registry.tick(500)
        assert placement.room_id in registry._sessions_by_room_id  # grace period not over yet
        assert placement.room_id in registry._connections_by_room_id

        registry.tick(600)  # 500 + 600 > 1000ms grace period
        assert placement.room_id not in registry._sessions_by_room_id
        assert placement.room_id not in registry._connections_by_room_id

        registry.tick(16)  # a tick after closure must not raise or resurrect the room
        assert placement.room_id not in registry._sessions_by_room_id

        # The client eventually disconnecting after the room is already gone must be a no-op.
        await registry.remove_participant(participant)

    asyncio.run(scenario())


def test_close_room_resets_still_connected_participants_back_to_the_lobby():
    async def scenario():
        registry = GameRoomRegistry(
            lambda connection, payload: None, _FakeRatingStore(), _make_directory(), room_close_grace_seconds=1,
        )
        white_participant = _make_participant("white")
        black_participant = _make_participant("black")
        placement = registry.create_private_room(white_participant)
        registry.join_private_room(black_participant, placement.join_code)

        placement.session.components.engine.resign(PieceColor.WHITE)
        registry.tick(1100)  # past the 1s grace period

        assert placement.room_id not in registry._sessions_by_room_id
        for participant in (white_participant, black_participant):
            assert participant.state is ParticipantState.LOBBY
            assert participant.room_id is None
            assert participant.role is None

    asyncio.run(scenario())


def test_close_room_removes_the_directory_entries_for_room_users_and_join_code():
    async def scenario():
        directory = _make_directory()
        registry = GameRoomRegistry(
            lambda connection, payload: None, _FakeRatingStore(), directory, room_close_grace_seconds=1,
        )
        white_participant = _make_participant("white")
        black_participant = _make_participant("black")
        placement = registry.create_private_room(white_participant)
        registry.join_private_room(black_participant, placement.join_code)

        placement.session.components.engine.resign(PieceColor.WHITE)
        registry.tick(1100)

        assert directory.get_room_owner(placement.room_id) is None
        assert directory.get_room_for_username("white") is None
        assert directory.get_room_for_username("black") is None
        assert directory.reserve_join(placement.join_code, "someone-else") is None

    asyncio.run(scenario())


def test_close_room_does_not_touch_a_participant_that_already_disconnected():
    async def scenario():
        registry = GameRoomRegistry(
            lambda connection, payload: None, _FakeRatingStore(), _make_directory(), room_close_grace_seconds=1,
        )
        white_participant = _make_participant("white")
        black_participant = _make_participant("black")
        placement = registry.create_private_room(white_participant)
        registry.join_private_room(black_participant, placement.join_code)

        await registry.remove_participant(white_participant)  # drops mid-game, before it ends
        room_id_seen_by_white_before_close = white_participant.room_id

        placement.session.components.engine.resign(PieceColor.WHITE)  # black wins
        registry.tick(1100)

        assert placement.room_id not in registry._sessions_by_room_id
        assert black_participant.state is ParticipantState.LOBBY
        assert black_participant.room_id is None
        assert black_participant.role is None
        # white already left before the room closed - _close_room must not reach for it
        assert white_participant.room_id == room_id_seen_by_white_before_close

    asyncio.run(scenario())


def test_close_room_removes_the_directory_entry_of_a_participant_who_disconnected_mid_game():
    # Regression test: a participant who disconnects mid-game is dropped from
    # _participants_by_room_id right away (see remove_participant), so _close_room used to
    # build its directory-cleanup usernames list only from whoever was still connected -
    # the disconnected player's directory:user:{username} entry survived the room closing
    # and falsely reported them as "already in a room" on their next create/join attempt.
    async def scenario():
        directory = _make_directory()
        registry = GameRoomRegistry(
            lambda connection, payload: None, _FakeRatingStore(), directory, room_close_grace_seconds=1,
        )
        white_participant = _make_participant("white")
        black_participant = _make_participant("black")
        placement = registry.create_private_room(white_participant)
        registry.join_private_room(black_participant, placement.join_code)

        await registry.remove_participant(white_participant)  # drops mid-game, before it ends
        assert directory.get_room_for_username("white") == placement.room_id  # still reserved while the game is live

        placement.session.components.engine.resign(PieceColor.WHITE)  # black wins
        registry.tick(1100)  # past the grace period - room closes

        assert placement.room_id not in registry._sessions_by_room_id
        assert directory.get_room_for_username("white") is None
        assert directory.get_room_for_username("black") is None

        # white must be able to open a brand-new room - no false "already in a room".
        new_white_participant = Participant(connection="conn-white-2", username="white")
        new_placement = registry.create_private_room(new_white_participant)
        assert new_placement.room_id != placement.room_id

        await registry.remove_participant(new_white_participant)

    asyncio.run(scenario())


def test_close_room_resets_a_reconnected_participant_not_the_stale_pre_reconnect_one():
    async def scenario():
        registry = GameRoomRegistry(
            lambda connection, payload: None, _FakeRatingStore(), _make_directory(), room_close_grace_seconds=1,
        )
        white_participant = Participant(connection="conn-white", username="alice")
        black_participant = Participant(connection="conn-black", username="bob")
        placement = registry.create_private_room(white_participant)
        registry.join_private_room(black_participant, placement.join_code)

        await registry.remove_participant(white_participant)  # alice drops, countdown starts
        reconnected = Participant(connection="conn-white-new", username="alice")
        assert registry.try_reconnect(reconnected) is not None

        placement.session.components.engine.resign(PieceColor.BLACK)  # alice (white) wins
        registry.tick(1100)

        assert placement.room_id not in registry._sessions_by_room_id
        assert reconnected.state is ParticipantState.LOBBY
        assert reconnected.room_id is None
        assert reconnected.role is None
        assert black_participant.state is ParticipantState.LOBBY
        # the stale pre-reconnect participant object was never re-touched by the close
        assert white_participant.role == "white"

    asyncio.run(scenario())


def test_room_stays_open_while_the_game_is_still_in_progress():
    async def scenario():
        registry, sent = _make_registry()
        participant = _make_participant("a")
        placement = registry.create_private_room(participant)

        registry.tick(16)
        registry.tick(16)

        assert placement.room_id in registry._sessions_by_room_id
        assert placement.session.components.engine.game_over is False

        await registry.remove_participant(participant)

    asyncio.run(scenario())


def test_create_matched_room_sends_role_and_snapshot_to_both_connections_with_correct_colors():
    async def scenario():
        registry, sent = _make_registry()
        white_participant = Participant(connection="conn-white", username="alice", rating=1200)
        black_participant = Participant(connection="conn-black", username="bob", rating=1180)

        registry.create_matched_room(white_participant, black_participant)

        assert white_participant.role == "white"
        assert black_participant.role == "black"
        assert white_participant.state is ParticipantState.IN_ROOM
        assert black_participant.state is ParticipantState.IN_ROOM
        assert white_participant.room_id == black_participant.room_id

        white_payloads = [payload for connection, payload in sent if connection == "conn-white"]
        black_payloads = [payload for connection, payload in sent if connection == "conn-black"]
        assert [p["type"] for p in white_payloads] == ["RoleAssigned", "GameSnapshot"]
        assert [p["type"] for p in black_payloads] == ["RoleAssigned", "GameSnapshot"]
        assert white_payloads[0]["role"] == "white"
        assert black_payloads[0]["role"] == "black"

        await registry.remove_participant(white_participant)
        await registry.remove_participant(black_participant)

    asyncio.run(scenario())


def test_create_matched_room_rejects_a_reservation_conflict_and_notifies_both_sides():
    async def scenario():
        registry, sent = _make_registry()
        white_participant = Participant(connection="conn-white", username="alice", rating=1200)
        black_participant = Participant(connection="conn-black", username="bob", rating=1180)
        registry._directory.reserve_new_room("room-elsewhere", ["bob"])  # bob is already seated

        registry.create_matched_room(white_participant, black_participant)

        assert white_participant.state is ParticipantState.LOBBY
        assert black_participant.state is ParticipantState.LOBBY
        white_payloads = [payload for connection, payload in sent if connection == "conn-white"]
        black_payloads = [payload for connection, payload in sent if connection == "conn-black"]
        assert [p["type"] for p in white_payloads] == ["MatchNotFound"]
        assert [p["type"] for p in black_payloads] == ["MatchNotFound"]

    asyncio.run(scenario())


def test_try_reconnect_places_a_new_connection_back_into_its_old_room_and_seat():
    async def scenario():
        registry, _ = _make_registry()
        white_participant = Participant(connection="conn-white", username="alice")
        black_participant = Participant(connection="conn-black", username="bob")
        placement = registry.create_private_room(white_participant)
        registry.join_private_room(black_participant, placement.join_code)

        await registry.remove_participant(white_participant)  # alice drops mid-game, countdown starts

        reconnecting_participant = Participant(connection="conn-white-new", username="alice")
        result = registry.try_reconnect(reconnecting_participant)

        assert result is not None
        assert result.room_id == placement.room_id
        assert result.role == "white"
        assert reconnecting_participant.role == "white"
        assert reconnecting_participant.room_id == placement.room_id
        assert reconnecting_participant.state is ParticipantState.IN_ROOM
        assert "conn-white-new" in registry._connections_by_room_id[placement.room_id]

        await registry.remove_participant(reconnecting_participant)
        await registry.remove_participant(black_participant)

    asyncio.run(scenario())


def test_try_reconnect_with_no_matching_disconnected_username_returns_none():
    async def scenario():
        registry, _ = _make_registry()
        participant = _make_participant("a")
        registry.create_private_room(participant)

        stranger = Participant(connection="conn-stranger", username="nobody")
        result = registry.try_reconnect(stranger)

        assert result is None
        assert stranger.state is ParticipantState.CONNECTED

        await registry.remove_participant(participant)

    asyncio.run(scenario())


def test_create_matched_room_wires_a_real_rating_store_into_the_sessions_rating_flow():
    async def scenario():
        reset_users_table()
        user_store = UserStore()
        rating_store = RatingStore()
        user_store.create_or_verify("alice", "hunter2")
        user_store.create_or_verify("bob", "hunter2")
        registry, _ = _make_registry(rating_store=rating_store)
        white_participant = Participant(connection="conn-white", username="alice")
        black_participant = Participant(connection="conn-black", username="bob")

        registry.create_matched_room(white_participant, black_participant)
        session = registry.game_session_for(white_participant)

        event = GameOverEvent(winner_color=PieceColor.BLACK, at_ms=100)
        session.components.dispatcher.publish(event)

        assert rating_store.get_rating("alice") == 1184
        assert rating_store.get_rating("bob") == 1216

        await registry.remove_participant(white_participant)
        await registry.remove_participant(black_participant)

    asyncio.run(scenario())
