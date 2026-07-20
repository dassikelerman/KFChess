import constants
from events.game_events import IllegalActionEvent
from events.serialization import JumpIntent, MoveIntent, to_dict
from model.position import Position
from server.session import Session

BOARD = ["wK .", ". ."]


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


def test_tick_advances_the_engines_clock():
    session = Session(BOARD)
    before = session.components.engine.clock

    session.tick(500)

    assert session.components.engine.clock == before + 500


def test_handle_client_message_with_a_valid_move_intent_moves_the_piece():
    session = Session(["wR . .", ". . .", ". . ."])
    intent_dict = to_dict(MoveIntent(source=Position(0, 0), destination=Position(0, 2)))

    session.handle_client_message("conn-a", intent_dict)
    session.tick(constants.MOVE_DURATION * 2)

    board = session.components.board
    assert board.piece_at(Position(0, 2)) is not None
    assert board.piece_at(Position(0, 0)) is None


def test_handle_client_message_with_an_invalid_move_intent_does_not_move_the_piece():
    # A knight can't move one cell in a straight line - rejected by
    # RuleEngine before anything reaches the board.
    session = Session(["wN . .", ". . .", ". . ."])
    intent_dict = to_dict(MoveIntent(source=Position(0, 0), destination=Position(0, 1)))

    session.handle_client_message("conn-a", intent_dict)

    board = session.components.board
    assert board.piece_at(Position(0, 0)) is not None
    assert board.piece_at(Position(0, 1)) is None


def test_handle_client_message_with_an_invalid_move_intent_still_publishes_illegal_action_event():
    session = Session(["wN . .", ". . .", ". . ."])
    collected = []
    session.components.dispatcher.subscribe(IllegalActionEvent, collected.append)
    intent_dict = to_dict(MoveIntent(source=Position(0, 0), destination=Position(0, 1)))

    session.handle_client_message("conn-a", intent_dict)

    assert len(collected) == 1
    assert collected[0].destination == Position(0, 1)


def test_handle_client_message_with_a_jump_intent_starts_a_jump():
    session = Session(["wR . .", ". . .", ". . ."])
    intent_dict = to_dict(JumpIntent(position=Position(0, 0)))

    session.handle_client_message("conn-a", intent_dict)

    assert session.components.engine.is_busy(Position(0, 0)) is True
