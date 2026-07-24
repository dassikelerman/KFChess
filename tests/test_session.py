import inspect

import constants
import server.session as session_module
from events.game_events import (
    GameOverEvent,
    IllegalActionEvent,
    MoveCompletedEvent,
    PlayerDisconnectedEvent,
    PlayerReconnectedEvent,
)
from model.piece import PieceColor
from model.position import Position
from protocol.game_messages import JumpIntent, MoveIntent
from server.session import GameSession

BOARD = ["wK .", ". ."]


class FakeNetworkPublisher:
    def __init__(self):
        self.unicast_calls = []

    def unicast(self, connection, event):
        self.unicast_calls.append((connection, event))


class FakeRatingStore:
    def __init__(self):
        self.update_ratings_calls = []

    def update_ratings(self, white_username, black_username, winner_color):
        self.update_ratings_calls.append((white_username, black_username, winner_color))
        return (0, 0)  # return value unused by GameSession


def _make_session(board=BOARD, network_publisher=None, **kwargs):
    if network_publisher is None:
        network_publisher = FakeNetworkPublisher()
    return GameSession(board, make_network_publisher=lambda dispatcher: network_publisher, **kwargs)


# -- construction -------------------------------------------------------------


def test_a_freshly_constructed_session_already_has_a_working_network_publisher():
    # Full construction, no session.network_publisher = ... assignment afterward - a
    # rejection must be able to reach the publisher immediately after __init__ returns.
    network_publisher = FakeNetworkPublisher()
    session = _make_session(["wR . .", ". . ."], network_publisher=network_publisher)
    session.assign_role("conn-a")  # white

    session.handle_move("conn-a", MoveIntent(source=Position(1, 1), destination=Position(1, 2)))  # empty source

    assert len(network_publisher.unicast_calls) == 1


def test_session_module_has_no_json_or_websocket_specific_dependencies():
    # GameSession must stay fully decoupled from the wire format - it receives typed
    # MoveIntent/JumpIntent objects and never touches json or websockets itself.
    source = inspect.getsource(session_module)
    assert "import json" not in source
    assert "websockets" not in source


# -- roles ----------------------------------------------------------------------


def test_first_connection_is_assigned_white():
    session = _make_session()
    assert session.assign_role("conn-a") == "white"


def test_second_connection_is_assigned_black():
    session = _make_session()
    session.assign_role("conn-a")
    assert session.assign_role("conn-b") == "black"


def test_third_and_later_connections_are_assigned_spectator():
    session = _make_session()
    session.assign_role("conn-a")
    session.assign_role("conn-b")
    assert session.assign_role("conn-c") == "spectator"
    assert session.assign_role("conn-d") == "spectator"


def test_asking_again_for_the_same_connection_returns_its_existing_role():
    session = _make_session()
    first = session.assign_role("conn-a")
    again = session.assign_role("conn-a")
    assert first == again == "white"


# -- login ----------------------------------------------------------------------


def test_record_login_stores_the_connections_username():
    session = _make_session()

    session.record_login("conn-a", "alice")

    assert session._usernames["conn-a"] == "alice"


def test_tick_advances_the_engines_clock():
    session = _make_session()
    before = session.components.engine.clock

    session.tick(500)

    assert session.components.engine.clock == before + 500


# -- typed move/jump handling: no object -> dict -> object round trip -----------


def test_handle_move_accepts_a_typed_move_intent_directly_and_moves_the_piece():
    session = _make_session(["wR . .", ". . .", ". . ."])
    session.assign_role("conn-a")  # white, owns the rook being moved

    session.handle_move("conn-a", MoveIntent(source=Position(0, 0), destination=Position(0, 2)))
    session.tick(constants.MOVE_DURATION * 2)

    board = session.components.board
    assert board.piece_at(Position(0, 2)) is not None
    assert board.piece_at(Position(0, 0)) is None


def test_handle_jump_accepts_a_typed_jump_intent_directly_and_starts_a_jump():
    session = _make_session(["wR . .", ". . .", ". . ."])
    session.assign_role("conn-a")  # white, owns the rook being jumped

    session.handle_jump("conn-a", JumpIntent(position=Position(0, 0)))

    assert session.components.engine.is_busy(Position(0, 0)) is True


# -- ownership enforcement ----------------------------------------------------


def test_white_connection_moving_a_black_piece_is_rejected_without_calling_the_engine():
    network_publisher = FakeNetworkPublisher()
    session = _make_session(["wR . .", ". . bP"], network_publisher=network_publisher)
    session.assign_role("conn-a")  # white
    engine_illegal_events = []
    session.components.dispatcher.subscribe(IllegalActionEvent, engine_illegal_events.append)

    session.handle_move("conn-a", MoveIntent(source=Position(1, 2), destination=Position(1, 1)))

    # GameEngine.request_move() was never called at all - it never got
    # the chance to publish its own internal IllegalActionEvent.
    assert engine_illegal_events == []
    assert len(network_publisher.unicast_calls) == 1
    connection, event = network_publisher.unicast_calls[0]
    assert connection == "conn-a"
    assert isinstance(event, IllegalActionEvent)
    assert event.destination == Position(1, 2)
    board = session.components.board
    assert board.piece_at(Position(1, 2)) is not None  # untouched


def test_black_connection_moving_a_white_piece_is_rejected_without_calling_the_engine():
    network_publisher = FakeNetworkPublisher()
    session = _make_session(["wR . .", ". . bP"], network_publisher=network_publisher)
    session.assign_role("conn-a")  # white
    session.assign_role("conn-b")  # black
    engine_illegal_events = []
    session.components.dispatcher.subscribe(IllegalActionEvent, engine_illegal_events.append)

    session.handle_move("conn-b", MoveIntent(source=Position(0, 0), destination=Position(0, 1)))

    assert engine_illegal_events == []
    assert len(network_publisher.unicast_calls) == 1
    connection, event = network_publisher.unicast_calls[0]
    assert connection == "conn-b"
    assert event.destination == Position(0, 0)
    board = session.components.board
    assert board.piece_at(Position(0, 0)) is not None
    assert board.piece_at(Position(0, 1)) is None


def test_spectator_attempting_a_move_is_rejected_without_calling_the_engine():
    network_publisher = FakeNetworkPublisher()
    session = _make_session(["wR . .", ". . ."], network_publisher=network_publisher)
    session.assign_role("conn-a")  # white
    session.assign_role("conn-b")  # black
    session.assign_role("conn-c")  # spectator

    session.handle_move("conn-c", MoveIntent(source=Position(0, 0), destination=Position(0, 1)))

    assert len(network_publisher.unicast_calls) == 1
    connection, event = network_publisher.unicast_calls[0]
    assert connection == "conn-c"
    board = session.components.board
    assert board.piece_at(Position(0, 0)) is not None
    assert board.piece_at(Position(0, 1)) is None


def test_spectator_attempting_a_jump_is_rejected_without_calling_the_engine():
    network_publisher = FakeNetworkPublisher()
    session = _make_session(["wR . .", ". . ."], network_publisher=network_publisher)
    session.assign_role("conn-a")  # white
    session.assign_role("conn-b")  # black
    session.assign_role("conn-c")  # spectator

    session.handle_jump("conn-c", JumpIntent(position=Position(0, 0)))

    assert len(network_publisher.unicast_calls) == 1
    assert session.components.engine.is_busy(Position(0, 0)) is False


def test_moving_from_an_empty_cell_is_rejected_with_no_piece_id():
    network_publisher = FakeNetworkPublisher()
    session = _make_session(["wR . .", ". . ."], network_publisher=network_publisher)
    session.assign_role("conn-a")  # white

    session.handle_move("conn-a", MoveIntent(source=Position(1, 1), destination=Position(1, 2)))

    assert len(network_publisher.unicast_calls) == 1
    connection, event = network_publisher.unicast_calls[0]
    assert connection == "conn-a"
    assert event.piece_id is None


# -- engine-level rejection (already the right color, still illegal) --------


def test_a_legitimate_engine_level_rejection_is_unicast_to_the_connection():
    network_publisher = FakeNetworkPublisher()
    session = _make_session(["wR . .", ". . .", ". . ."], network_publisher=network_publisher)
    session.assign_role("conn-a")  # white

    # Land a move so the piece enters its long rest (constants.LONG_REST_DURATION).
    session.handle_move("conn-a", MoveIntent(source=Position(0, 0), destination=Position(0, 1)))
    session.tick(constants.MOVE_DURATION + 1)

    session.handle_move("conn-a", MoveIntent(source=Position(0, 1), destination=Position(0, 2)))

    assert len(network_publisher.unicast_calls) == 1
    connection, event = network_publisher.unicast_calls[0]
    assert connection == "conn-a"
    assert isinstance(event, IllegalActionEvent)
    board = session.components.board
    assert board.piece_at(Position(0, 1)) is not None  # still resting in place
    assert board.piece_at(Position(0, 2)) is None


# -- a legitimate accepted action -------------------------------------------


def test_a_legitimate_accepted_move_does_not_unicast_anything():
    network_publisher = FakeNetworkPublisher()
    session = _make_session(["wR . .", ". . ."], network_publisher=network_publisher)
    session.assign_role("conn-a")  # white
    move_events = []
    session.components.dispatcher.subscribe(MoveCompletedEvent, move_events.append)

    session.handle_move("conn-a", MoveIntent(source=Position(0, 0), destination=Position(0, 1)))
    session.tick(constants.MOVE_DURATION + 1)

    assert network_publisher.unicast_calls == []
    assert len(move_events) == 1


# -- rating updates on game over ----------------------------------------------


def test_a_real_game_over_triggers_exactly_one_rating_update_with_correct_args():
    rating_store = FakeRatingStore()
    # White's rook can capture black's king outright in one straight-line
    # move - a real GameEngine win-condition check, not a hand-built
    # GameOverEvent, to prove GameSession is actually wired to the real thing.
    session = _make_session(["wR . bK", ". . .", ". . ."], rating_store=rating_store)
    session.assign_role("conn-white")  # white
    session.assign_role("conn-black")  # black
    session.record_login("conn-white", "alice")
    session.record_login("conn-black", "bob")

    session.handle_move("conn-white", MoveIntent(source=Position(0, 0), destination=Position(0, 2)))
    session.tick(constants.MOVE_DURATION * 2 + 1)  # distance 2 - duration scales with distance

    assert rating_store.update_ratings_calls == [("alice", "bob", "white")]


def test_a_missing_username_for_a_seat_skips_the_rating_update_without_crashing():
    rating_store = FakeRatingStore()
    session = _make_session(["wR . bK", ". . .", ". . ."], rating_store=rating_store)
    session.assign_role("conn-white")  # white
    session.assign_role("conn-black")  # black
    session.record_login("conn-white", "alice")
    # conn-black never logs in - no username recorded for the black seat.

    session.handle_move("conn-white", MoveIntent(source=Position(0, 0), destination=Position(0, 2)))
    session.tick(constants.MOVE_DURATION * 2 + 1)  # must not raise

    assert rating_store.update_ratings_calls == []


def test_game_over_event_firing_twice_only_updates_ratings_once():
    rating_store = FakeRatingStore()
    session = _make_session(rating_store=rating_store)
    session.assign_role("conn-white")  # white
    session.assign_role("conn-black")  # black
    session.record_login("conn-white", "alice")
    session.record_login("conn-black", "bob")

    event = GameOverEvent(winner_color=PieceColor.WHITE, at_ms=100)
    session.components.dispatcher.publish(event)
    session.components.dispatcher.publish(event)  # must not double-count

    assert rating_store.update_ratings_calls == [("alice", "bob", "white")]


def test_a_session_built_without_a_rating_store_does_not_subscribe_to_game_over():
    session = _make_session()  # rating_store defaults to None
    session.assign_role("conn-white")
    session.assign_role("conn-black")
    session.record_login("conn-white", "alice")
    session.record_login("conn-black", "bob")

    # Must not raise even though there's no rating_store to call into.
    session.components.dispatcher.publish(GameOverEvent(winner_color=PieceColor.WHITE, at_ms=100))


# -- disconnect countdown: driven only by tick(dt_ms), no asyncio task/sleep ----


def test_a_full_disconnect_countdown_publishes_each_second_and_resigns_at_zero():
    session = _make_session(disconnect_countdown_seconds=3)
    session.assign_role("conn-a")  # white
    session.assign_role("conn-b")  # black
    disconnect_events = []
    game_over_events = []
    session.components.dispatcher.subscribe(PlayerDisconnectedEvent, disconnect_events.append)
    session.components.dispatcher.subscribe(GameOverEvent, game_over_events.append)

    session.begin_disconnect_countdown("conn-a")  # white drops, publishes 3 immediately
    session.tick(1000)
    session.tick(1000)
    session.tick(1000)

    assert [e.seconds_remaining for e in disconnect_events] == [3, 2, 1, 0]
    assert all(e.color == PieceColor.WHITE for e in disconnect_events)
    assert session.components.engine.game_over is True
    assert len(game_over_events) == 1
    assert game_over_events[0].winner_color == PieceColor.BLACK
    assert session._countdowns_by_color == {}


def test_a_spectator_disconnect_does_not_start_a_countdown():
    session = _make_session()
    session.assign_role("conn-a")  # white
    session.assign_role("conn-b")  # black
    session.assign_role("conn-c")  # spectator

    session.begin_disconnect_countdown("conn-c")

    assert session._countdowns_by_color == {}


def test_the_game_ending_for_another_reason_stops_the_countdown_before_the_next_publish():
    session = _make_session(disconnect_countdown_seconds=5)
    session.assign_role("conn-a")  # white
    session.assign_role("conn-b")  # black
    disconnect_events = []
    session.components.dispatcher.subscribe(PlayerDisconnectedEvent, disconnect_events.append)

    session.begin_disconnect_countdown("conn-a")  # white drops, publishes 5 immediately
    session.components.engine.resign(PieceColor.BLACK)  # game ends independently
    session.tick(1000)  # would have published 4, but the game is already over

    assert [e.seconds_remaining for e in disconnect_events] == [5]
    assert session._countdowns_by_color == {}


def test_a_large_tick_jumps_straight_to_the_correct_remaining_second_and_resigns():
    # A single tick can be far larger than 1000ms (a slow server tick, or a room that
    # was idle for a while) - the countdown must not require one tick per second.
    session = _make_session(disconnect_countdown_seconds=20)
    session.assign_role("conn-a")  # white
    session.assign_role("conn-b")  # black
    disconnect_events = []
    session.components.dispatcher.subscribe(PlayerDisconnectedEvent, disconnect_events.append)

    session.begin_disconnect_countdown("conn-a")  # publishes 20 immediately
    session.tick(45_000)  # one huge tick, far past the 20s deadline

    assert [e.seconds_remaining for e in disconnect_events] == [20, 0]
    assert session.components.engine.game_over is True
    assert session._countdowns_by_color == {}


def test_a_sub_second_tick_does_not_publish_a_duplicate_event_for_the_same_second():
    session = _make_session(disconnect_countdown_seconds=5)
    session.assign_role("conn-a")  # white
    session.assign_role("conn-b")  # black
    disconnect_events = []
    session.components.dispatcher.subscribe(PlayerDisconnectedEvent, disconnect_events.append)

    session.begin_disconnect_countdown("conn-a")  # publishes 5 immediately
    session.tick(100)  # 5000ms -> 4900ms, still displays as "5"

    assert [e.seconds_remaining for e in disconnect_events] == [5]


def test_reconnecting_within_the_grace_window_cancels_the_countdown_and_swaps_the_connection():
    session = _make_session(disconnect_countdown_seconds=20)
    session.assign_role("conn-a")  # white
    session.assign_role("conn-b")  # black
    session.record_login("conn-a", "alice")
    session.record_login("conn-b", "bob")
    reconnected_events = []
    session.components.dispatcher.subscribe(PlayerReconnectedEvent, reconnected_events.append)

    session.begin_disconnect_countdown("conn-a")

    role = session.reconnect("conn-a-new", "alice")

    assert role == "white"
    assert session._roles["conn-a-new"] == "white"
    assert session._usernames["conn-a-new"] == "alice"
    assert "conn-a" not in session._roles
    assert "conn-a" not in session._usernames
    assert session._countdowns_by_color == {}
    assert [e.color for e in reconnected_events] == [PieceColor.WHITE]

    session.tick(20_000 + 1000)  # even a tick past the original deadline must not resign
    assert session.components.engine.game_over is False


def test_reconnecting_a_username_with_no_active_countdown_fails():
    session = _make_session()
    session.assign_role("conn-a")  # white, still connected
    session.record_login("conn-a", "alice")

    assert session.reconnect("conn-a-new", "alice") is None


def test_reconnecting_an_unknown_username_fails():
    session = _make_session()

    assert session.reconnect("conn-a-new", "nobody") is None


def test_reconnecting_after_the_countdown_already_resigned_fails():
    session = _make_session(disconnect_countdown_seconds=1)
    session.assign_role("conn-a")  # white
    session.assign_role("conn-b")  # black
    session.record_login("conn-a", "alice")
    session.record_login("conn-b", "bob")

    session.begin_disconnect_countdown("conn-a")
    session.tick(1000)  # runs the countdown to zero and resigns

    assert session.reconnect("conn-a-new", "alice") is None


def test_a_duplicate_disconnect_signal_does_not_start_a_second_countdown():
    session = _make_session(disconnect_countdown_seconds=5)
    session.assign_role("conn-a")  # white
    session.assign_role("conn-b")  # black

    session.begin_disconnect_countdown("conn-a")
    first_countdown = session._countdowns_by_color[PieceColor.WHITE]

    session.begin_disconnect_countdown("conn-a")  # duplicate signal for the same connection
    second_countdown = session._countdowns_by_color[PieceColor.WHITE]

    assert first_countdown is second_countdown
