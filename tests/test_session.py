import constants
from events.game_events import GameOverEvent, IllegalActionEvent, MoveCompletedEvent
from protocol.serialization import JumpIntent, MoveIntent, to_dict
from model.piece import PieceColor
from model.position import Position
from server.session import Session

BOARD = ["wK .", ". ."]


class FakeNetworkPublisher:
    def __init__(self):
        self.unicast_calls = []

    def unicast(self, connection, event):
        self.unicast_calls.append((connection, event))


class FakeUserStore:
    def __init__(self):
        self.update_ratings_calls = []

    def update_ratings(self, white_username, black_username, winner_color):
        self.update_ratings_calls.append((white_username, black_username, winner_color))
        return (0, 0)  # return value unused by Session


def test_first_connection_is_assigned_white():
    session = Session(BOARD)
    assert session.assign_role("conn-a") == "white"


def test_second_connection_is_assigned_black():
    session = Session(BOARD)
    session.assign_role("conn-a")
    assert session.assign_role("conn-b") == "black"


def test_third_and_later_connections_are_assigned_spectator():
    session = Session(BOARD)
    session.assign_role("conn-a")
    session.assign_role("conn-b")
    assert session.assign_role("conn-c") == "spectator"
    assert session.assign_role("conn-d") == "spectator"


def test_asking_again_for_the_same_connection_returns_its_existing_role():
    session = Session(BOARD)
    first = session.assign_role("conn-a")
    again = session.assign_role("conn-a")
    assert first == again == "white"


# -- login / disconnect -------------------------------------------------------


def test_record_login_stores_the_connections_username():
    session = Session(BOARD)

    session.record_login("conn-a", "alice")

    assert session._usernames["conn-a"] == "alice"


def test_disconnect_removes_the_connection_from_both_the_username_and_role_mappings():
    session = Session(BOARD)
    session.record_login("conn-a", "alice")
    session.assign_role("conn-a")

    session.disconnect("conn-a")

    assert "conn-a" not in session._usernames
    assert "conn-a" not in session._roles


def test_disconnect_on_a_connection_that_never_logged_in_does_not_raise():
    session = Session(BOARD)
    session.disconnect("conn-never-connected")  # must not raise


def test_tick_advances_the_engines_clock():
    session = Session(BOARD)
    before = session.components.engine.clock

    session.tick(500)

    assert session.components.engine.clock == before + 500


def test_handle_client_message_with_a_valid_move_intent_moves_the_piece():
    session = Session(["wR . .", ". . .", ". . ."])
    session.assign_role("conn-a")  # white, owns the rook being moved
    intent_dict = to_dict(MoveIntent(source=Position(0, 0), destination=Position(0, 2)))

    session.handle_client_message("conn-a", intent_dict)
    session.tick(constants.MOVE_DURATION * 2)

    board = session.components.board
    assert board.piece_at(Position(0, 2)) is not None
    assert board.piece_at(Position(0, 0)) is None


def test_handle_client_message_with_a_jump_intent_starts_a_jump():
    session = Session(["wR . .", ". . .", ". . ."])
    session.assign_role("conn-a")  # white, owns the rook being jumped
    intent_dict = to_dict(JumpIntent(position=Position(0, 0)))

    session.handle_client_message("conn-a", intent_dict)

    assert session.components.engine.is_busy(Position(0, 0)) is True


# -- ownership enforcement ----------------------------------------------------


def test_white_connection_moving_a_black_piece_is_rejected_without_calling_the_engine():
    session = Session(["wR . .", ". . bP"])
    session.assign_role("conn-a")  # white
    network_publisher = FakeNetworkPublisher()
    session.network_publisher = network_publisher
    engine_illegal_events = []
    session.components.dispatcher.subscribe(IllegalActionEvent, engine_illegal_events.append)

    session.handle_client_message("conn-a", to_dict(MoveIntent(source=Position(1, 2), destination=Position(1, 1))))

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
    session = Session(["wR . .", ". . bP"])
    session.assign_role("conn-a")  # white
    session.assign_role("conn-b")  # black
    network_publisher = FakeNetworkPublisher()
    session.network_publisher = network_publisher
    engine_illegal_events = []
    session.components.dispatcher.subscribe(IllegalActionEvent, engine_illegal_events.append)

    session.handle_client_message("conn-b", to_dict(MoveIntent(source=Position(0, 0), destination=Position(0, 1))))

    assert engine_illegal_events == []
    assert len(network_publisher.unicast_calls) == 1
    connection, event = network_publisher.unicast_calls[0]
    assert connection == "conn-b"
    assert event.destination == Position(0, 0)
    board = session.components.board
    assert board.piece_at(Position(0, 0)) is not None
    assert board.piece_at(Position(0, 1)) is None


def test_spectator_attempting_a_move_is_rejected_without_calling_the_engine():
    session = Session(["wR . .", ". . ."])
    session.assign_role("conn-a")  # white
    session.assign_role("conn-b")  # black
    session.assign_role("conn-c")  # spectator
    network_publisher = FakeNetworkPublisher()
    session.network_publisher = network_publisher

    session.handle_client_message("conn-c", to_dict(MoveIntent(source=Position(0, 0), destination=Position(0, 1))))

    assert len(network_publisher.unicast_calls) == 1
    connection, event = network_publisher.unicast_calls[0]
    assert connection == "conn-c"
    board = session.components.board
    assert board.piece_at(Position(0, 0)) is not None
    assert board.piece_at(Position(0, 1)) is None


def test_spectator_attempting_a_jump_is_rejected_without_calling_the_engine():
    session = Session(["wR . .", ". . ."])
    session.assign_role("conn-a")  # white
    session.assign_role("conn-b")  # black
    session.assign_role("conn-c")  # spectator
    network_publisher = FakeNetworkPublisher()
    session.network_publisher = network_publisher

    session.handle_client_message("conn-c", to_dict(JumpIntent(position=Position(0, 0))))

    assert len(network_publisher.unicast_calls) == 1
    assert session.components.engine.is_busy(Position(0, 0)) is False


def test_moving_from_an_empty_cell_is_rejected_with_no_piece_id():
    session = Session(["wR . .", ". . ."])
    session.assign_role("conn-a")  # white
    network_publisher = FakeNetworkPublisher()
    session.network_publisher = network_publisher

    session.handle_client_message("conn-a", to_dict(MoveIntent(source=Position(1, 1), destination=Position(1, 2))))

    assert len(network_publisher.unicast_calls) == 1
    connection, event = network_publisher.unicast_calls[0]
    assert connection == "conn-a"
    assert event.piece_id is None


# -- engine-level rejection (already the right color, still illegal) --------


def test_a_legitimate_engine_level_rejection_is_unicast_to_the_connection():
    session = Session(["wR . .", ". . .", ". . ."])
    session.assign_role("conn-a")  # white
    network_publisher = FakeNetworkPublisher()
    session.network_publisher = network_publisher

    # Land a move so the piece enters its long rest (constants.LONG_REST_DURATION).
    session.handle_client_message("conn-a", to_dict(MoveIntent(source=Position(0, 0), destination=Position(0, 1))))
    session.tick(constants.MOVE_DURATION + 1)

    session.handle_client_message("conn-a", to_dict(MoveIntent(source=Position(0, 1), destination=Position(0, 2))))

    assert len(network_publisher.unicast_calls) == 1
    connection, event = network_publisher.unicast_calls[0]
    assert connection == "conn-a"
    assert isinstance(event, IllegalActionEvent)
    board = session.components.board
    assert board.piece_at(Position(0, 1)) is not None  # still resting in place
    assert board.piece_at(Position(0, 2)) is None


# -- a legitimate accepted action -------------------------------------------


def test_a_legitimate_accepted_move_does_not_unicast_anything():
    session = Session(["wR . .", ". . ."])
    session.assign_role("conn-a")  # white
    network_publisher = FakeNetworkPublisher()
    session.network_publisher = network_publisher
    move_events = []
    session.components.dispatcher.subscribe(MoveCompletedEvent, move_events.append)

    session.handle_client_message("conn-a", to_dict(MoveIntent(source=Position(0, 0), destination=Position(0, 1))))
    session.tick(constants.MOVE_DURATION + 1)

    assert network_publisher.unicast_calls == []
    assert len(move_events) == 1


# -- Feature 4: rating updates on game over ----------------------------------


def test_a_real_game_over_triggers_exactly_one_rating_update_with_correct_args():
    user_store = FakeUserStore()
    # White's rook can capture black's king outright in one straight-line
    # move - a real GameEngine win-condition check, not a hand-built
    # GameOverEvent, to prove Session is actually wired to the real thing.
    session = Session(["wR . bK", ". . .", ". . ."], user_store=user_store)
    session.assign_role("conn-white")  # white
    session.assign_role("conn-black")  # black
    session.record_login("conn-white", "alice")
    session.record_login("conn-black", "bob")
    session.network_publisher = FakeNetworkPublisher()

    session.handle_client_message(
        "conn-white", to_dict(MoveIntent(source=Position(0, 0), destination=Position(0, 2))),
    )
    session.tick(constants.MOVE_DURATION * 2 + 1)  # distance 2 - duration scales with distance

    assert user_store.update_ratings_calls == [("alice", "bob", "white")]


def test_a_missing_username_for_a_seat_skips_the_rating_update_without_crashing():
    user_store = FakeUserStore()
    session = Session(["wR . bK", ". . .", ". . ."], user_store=user_store)
    session.assign_role("conn-white")  # white
    session.assign_role("conn-black")  # black
    session.record_login("conn-white", "alice")
    # conn-black never logs in - no username recorded for the black seat.
    session.network_publisher = FakeNetworkPublisher()

    session.handle_client_message(
        "conn-white", to_dict(MoveIntent(source=Position(0, 0), destination=Position(0, 2))),
    )
    session.tick(constants.MOVE_DURATION * 2 + 1)  # must not raise

    assert user_store.update_ratings_calls == []


def test_game_over_event_firing_twice_only_updates_ratings_once():
    user_store = FakeUserStore()
    session = Session(BOARD, user_store=user_store)
    session.assign_role("conn-white")  # white
    session.assign_role("conn-black")  # black
    session.record_login("conn-white", "alice")
    session.record_login("conn-black", "bob")

    event = GameOverEvent(winner_color=PieceColor.WHITE, at_ms=100)
    session.components.dispatcher.publish(event)
    session.components.dispatcher.publish(event)  # must not double-count

    assert user_store.update_ratings_calls == [("alice", "bob", "white")]


def test_a_session_built_without_a_user_store_does_not_subscribe_to_game_over():
    session = Session(BOARD)  # user_store defaults to None
    session.assign_role("conn-white")
    session.assign_role("conn-black")
    session.record_login("conn-white", "alice")
    session.record_login("conn-black", "bob")

    # Must not raise even though there's no user_store to call into.
    session.components.dispatcher.publish(GameOverEvent(winner_color=PieceColor.WHITE, at_ms=100))
