import asyncio

import constants
from events.game_events import GameOverEvent, PlayerDisconnectedEvent
from model.piece import PieceColor
from model.position import Position
from server.contracts import Participant, ParticipantState
from server.rating import RatingStore
from server.rooms import GameRoomRegistry, RoomPlacement
from server.user_store import UserStore


def _make_registry(rating_store=None):
    sent = []

    def send_fn(connection, payload):
        sent.append((connection, payload))

    if rating_store is None:
        rating_store = RatingStore(":memory:")
    return GameRoomRegistry(send_fn, rating_store), sent


def _make_participant(label):
    return Participant(connection=f"conn-{label}")


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


def test_generate_unique_room_id_retries_on_collision(monkeypatch):
    registry, _ = _make_registry()
    registry._sessions_by_room_id["aaaaaa"] = object()
    values = iter(["aaaaaa", "bbbbbb"])
    monkeypatch.setattr("server.rooms.secrets.token_hex", lambda n: next(values))

    room_id = registry._generate_unique_room_id()

    assert room_id == "bbbbbb"


def test_join_private_room_assigns_black_then_spectator_and_none_for_an_unknown_room():
    async def scenario():
        registry, _ = _make_registry()
        creator = _make_participant("a")
        placement = registry.create_private_room(creator)

        second = _make_participant("b")
        second_placement = registry.join_private_room(second, placement.room_id)
        assert second_placement.role == "black"
        assert second.role == "black"
        assert second.room_id == placement.room_id
        assert second.state is ParticipantState.IN_ROOM

        third = _make_participant("c")
        third_placement = registry.join_private_room(third, placement.room_id)
        assert third_placement.role == "spectator"

        assert registry.join_private_room(_make_participant("d"), "no-such-room") is None

        await registry.remove_participant(creator)
        await registry.remove_participant(second)
        await registry.remove_participant(third)

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
        registry.join_private_room(second, placement.room_id)

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

        registry = GameRoomRegistry(send_fn, RatingStore(":memory:"))
        failing_participant = Participant(connection=failing_connection)
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


def test_create_private_room_wires_a_real_rating_store_into_the_sessions_rating_flow(tmp_path):
    async def scenario():
        db_path = str(tmp_path / "test_users.db")
        user_store = UserStore(db_path)
        rating_store = RatingStore(db_path)
        user_store.create_or_verify("alice", "hunter2")
        user_store.create_or_verify("bob", "hunter2")
        registry, _ = _make_registry(rating_store=rating_store)
        white_participant = Participant(connection="conn-white", username="alice")
        black_participant = Participant(connection="conn-black", username="bob")

        placement = registry.create_private_room(white_participant)
        registry.join_private_room(black_participant, placement.room_id)

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
            lambda connection, payload: None, RatingStore(":memory:"), disconnect_countdown_seconds=2,
        )
        white_participant = _make_participant("white")
        black_participant = _make_participant("black")
        placement = registry.create_private_room(white_participant)
        registry.join_private_room(black_participant, placement.room_id)

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
        assert [p["type"] for p in white_payloads] == ["role", "GameSnapshot"]
        assert [p["type"] for p in black_payloads] == ["role", "GameSnapshot"]
        assert white_payloads[0]["role"] == "white"
        assert black_payloads[0]["role"] == "black"

        await registry.remove_participant(white_participant)
        await registry.remove_participant(black_participant)

    asyncio.run(scenario())


def test_try_reconnect_places_a_new_connection_back_into_its_old_room_and_seat():
    async def scenario():
        registry, _ = _make_registry()
        white_participant = Participant(connection="conn-white", username="alice")
        black_participant = Participant(connection="conn-black", username="bob")
        placement = registry.create_private_room(white_participant)
        registry.join_private_room(black_participant, placement.room_id)

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


def test_create_matched_room_wires_a_real_rating_store_into_the_sessions_rating_flow(tmp_path):
    async def scenario():
        db_path = str(tmp_path / "test_users.db")
        user_store = UserStore(db_path)
        rating_store = RatingStore(db_path)
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
