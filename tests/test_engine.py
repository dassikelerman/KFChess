import pytest

from model.board import Board
from model.position import Position
from rules.rule_engine import RuleEngine, build_default_registry
from engine.game_conditions import KingCaptureWinCondition, LastRankPromotion, WinCondition, PromotionRule
from realtime.real_time_arbiter import RealTimeArbiter
from input.board_mapper import BoardMapper
from input.controller import Controller
from engine.game_engine import GameEngine
from board_io.board_printer import BoardPrinter

CELL_SIZE = 100
MOVE_DURATION = 1000
JUMP_DURATION = 1000
EMPTY_CELL = "."


def get(board, row, col):
    piece = board.piece_at(Position(row, col))
    return EMPTY_CELL if piece is None else piece.color.value + piece.kind.value


def is_empty(board, row, col):
    return board.piece_at(Position(row, col)) is None


class NeverEndsWinCondition(WinCondition):
    """Fake collaborator used to test engine behaviour in isolation,
    injected instead of monkeypatching KingCaptureWinCondition."""

    def is_game_over(self, captured_piece):
        return False


class NoPromotion(PromotionRule):
    def promote(self, piece, row, board_height):
        return piece


def make_engine(rows, win_condition=None, promotion_rule=None):
    board = Board(rows)
    registry = build_default_registry(pawn_direction={"w": -1, "b": 1})
    engine = GameEngine(
        board=board,
        rule_engine=RuleEngine(registry),
        arbiter=RealTimeArbiter(board),
        win_condition=win_condition or KingCaptureWinCondition(),
        promotion_rule=promotion_rule or LastRankPromotion(),
        move_duration=MOVE_DURATION,
        jump_duration=JUMP_DURATION,
    )
    board_mapper = BoardMapper(CELL_SIZE, board.width, board.height)
    controller = Controller(engine, board_mapper)
    return engine, controller, board


def cell_to_pixel(row, col):
    return col * CELL_SIZE, row * CELL_SIZE


def test_click_selects_own_piece():
    engine, controller, board = make_engine([["wK", "."], [".", "."]])
    x, y = cell_to_pixel(0, 0)
    controller.click(x, y)
    assert controller.selected == (0, 0)


def test_click_out_of_bounds_is_ignored():
    engine, controller, board = make_engine([["wK", "."], [".", "."]])
    controller.click(-1, -1)
    assert controller.selected is None


def test_click_empty_cell_with_no_selection_is_ignored():
    engine, controller, board = make_engine([["wK", "."], [".", "."]])
    controller.click(*cell_to_pixel(0, 1))
    assert controller.selected is None
    assert get(board, 0, 0) == "wK"


def test_pixel_to_cell_matches_spec_examples():
    # click 50 50 -> center of the top-left cell (0, 0)
    # click 150 50 -> the next cell to the right (0, 1)
    engine, controller, board = make_engine([["wR", "wQ", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(50, 50)
    assert controller.selected == (0, 0)
    controller.click(150, 50)
    assert controller.selected == (0, 1)  # friendly piece: selection replaced, not moved
    assert get(board, 0, 0) == "wR"
    assert get(board, 0, 1) == "wQ"


def test_click_friendly_piece_replaces_selection():
    engine, controller, board = make_engine([["wR", "wQ", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    assert controller.selected == (0, 0)

    controller.click(*cell_to_pixel(0, 1))
    assert controller.selected == (0, 1)
    # no move was queued for either piece
    assert get(board, 0, 0) == "wR"
    assert get(board, 0, 1) == "wQ"


def test_click_on_busy_friendly_piece_does_not_replace_selection():
    engine, controller, board = make_engine([["wR", ".", "."], ["wB", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))  # rook move queued, (0, 0) now busy
    assert controller.selected is None

    controller.click(*cell_to_pixel(1, 0))  # select the bishop
    assert controller.selected == (1, 0)

    controller.click(*cell_to_pixel(0, 0))  # rook's old cell is still busy
    assert controller.selected == (1, 0)  # selection unchanged


def test_selecting_then_moving_starts_a_move():
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))

    assert controller.selected is None
    assert get(board, 0, 0) == "wR"  # piece stays at the source until the move lands


def test_move_lands_after_move_duration_elapses():
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))

    engine.wait(MOVE_DURATION * 2)  # 2-square move takes 2x as long
    assert get(board, 0, 2) == "wR"
    assert is_empty(board, 0, 0)


def test_move_does_not_land_before_duration_fully_elapses():
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))

    engine.wait(MOVE_DURATION * 2 - 1)  # one millisecond short of arrival
    assert get(board, 0, 0) == "wR"
    assert is_empty(board, 0, 2)


def test_wait_calls_accumulate_toward_arrival_time():
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))

    engine.wait(MOVE_DURATION)  # halfway there: still original position
    assert get(board, 0, 0) == "wR"
    assert is_empty(board, 0, 2)

    engine.wait(MOVE_DURATION)  # the rest of the duration: now it lands
    assert get(board, 0, 2) == "wR"
    assert is_empty(board, 0, 0)


def test_illegal_move_keeps_selection_and_piece_in_place():
    engine, controller, board = make_engine([["wN", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 1))  # not a legal knight move

    assert controller.selected == (0, 0)
    assert get(board, 0, 0) == "wN"


def test_king_legal_one_step_move_lands():
    engine, controller, board = make_engine([["wK", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(1, 1))
    engine.wait(MOVE_DURATION)

    assert get(board, 1, 1) == "wK"
    assert is_empty(board, 0, 0)


def test_king_illegal_two_cell_move_is_ignored():
    engine, controller, board = make_engine([["wK", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(2, 0))  # two cells: illegal for a king
    engine.wait(MOVE_DURATION * 2)

    assert controller.selected == (0, 0)
    assert get(board, 0, 0) == "wK"


def test_rook_illegal_diagonal_move_is_ignored():
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(2, 2))  # diagonal: illegal for a rook
    engine.wait(MOVE_DURATION * 2)

    assert controller.selected == (0, 0)
    assert get(board, 0, 0) == "wR"


def test_bishop_legal_diagonal_move_lands():
    engine, controller, board = make_engine([["wB", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(2, 2))
    engine.wait(MOVE_DURATION * 2)

    assert get(board, 2, 2) == "wB"
    assert is_empty(board, 0, 0)


def test_bishop_illegal_straight_move_is_ignored():
    engine, controller, board = make_engine([["wB", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))  # straight: illegal for a bishop
    engine.wait(MOVE_DURATION * 2)

    assert controller.selected == (0, 0)
    assert get(board, 0, 0) == "wB"


def test_queen_legal_straight_and_diagonal_moves_land():
    engine, controller, board = make_engine([["wQ", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))
    engine.wait(MOVE_DURATION * 2)
    assert get(board, 0, 2) == "wQ"

    controller.click(*cell_to_pixel(0, 2))
    controller.click(*cell_to_pixel(2, 0))
    engine.wait(MOVE_DURATION * 2)
    assert get(board, 2, 0) == "wQ"


def test_knight_legal_l_shape_move_lands():
    engine, controller, board = make_engine([["wN", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(2, 1))
    engine.wait(MOVE_DURATION * 2)

    assert get(board, 2, 1) == "wN"
    assert is_empty(board, 0, 0)


def test_rook_blocked_by_piece_is_ignored():
    engine, controller, board = make_engine([["wR", "bP", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))  # blocked by the piece at (0, 1)
    engine.wait(MOVE_DURATION * 2)

    assert controller.selected == (0, 0)
    assert get(board, 0, 0) == "wR"
    assert get(board, 0, 1) == "bP"


def test_bishop_blocked_by_piece_is_ignored():
    engine, controller, board = make_engine([["wB", ".", "."], [".", "bP", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(2, 2))  # blocked by the piece at (1, 1)
    engine.wait(MOVE_DURATION * 2)

    assert controller.selected == (0, 0)
    assert get(board, 0, 0) == "wB"
    assert get(board, 1, 1) == "bP"


def test_knight_jumps_over_blockers_and_lands():
    engine, controller, board = make_engine([["wN", "wP", "."], ["wP", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(2, 1))
    engine.wait(MOVE_DURATION * 2)

    assert get(board, 2, 1) == "wN"
    assert is_empty(board, 0, 0)
    # blockers were untouched, proving the knight jumped rather than moved through them
    assert get(board, 0, 1) == "wP"
    assert get(board, 1, 0) == "wP"


def test_move_captures_enemy_piece_at_destination():
    engine, controller, board = make_engine([["wR", ".", "bP"], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))
    engine.wait(MOVE_DURATION * 2)

    assert get(board, 0, 2) == "wR"
    assert is_empty(board, 0, 0)


def test_white_pawn_moves_upward():
    # 4-row board: white's start row is height - 1 = 3
    rows = [[".", ".", "."], [".", ".", "."], [".", ".", "."], ["wP", ".", "."]]
    engine, controller, board = make_engine(rows)
    controller.click(*cell_to_pixel(3, 0))
    controller.click(*cell_to_pixel(2, 0))
    engine.wait(MOVE_DURATION)

    assert get(board, 2, 0) == "wP"
    assert is_empty(board, 3, 0)


def test_black_pawn_moves_downward():
    rows = [["bP", ".", "."], [".", ".", "."], [".", ".", "."], [".", ".", "."]]
    engine, controller, board = make_engine(rows)
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(1, 0))
    engine.wait(MOVE_DURATION)

    assert get(board, 1, 0) == "bP"
    assert is_empty(board, 0, 0)


def test_pawn_double_step_off_start_row_is_ignored():
    # pawn sits on row 3, the back rank - not the pawn start row (2) on this 4-row board
    rows = [[".", ".", "."], [".", ".", "."], [".", ".", "."], ["wP", ".", "."]]
    engine, controller, board = make_engine(rows)
    controller.click(*cell_to_pixel(3, 0))
    controller.click(*cell_to_pixel(1, 0))
    engine.wait(MOVE_DURATION * 2)

    assert controller.selected == (3, 0)
    assert get(board, 3, 0) == "wP"


def test_pawn_cannot_capture_forward():
    rows = [[".", ".", "."], ["bP", ".", "."], ["wP", ".", "."], [".", ".", "."]]
    engine, controller, board = make_engine(rows)
    controller.click(*cell_to_pixel(2, 0))
    controller.click(*cell_to_pixel(1, 0))
    engine.wait(MOVE_DURATION)

    assert controller.selected == (2, 0)
    assert get(board, 2, 0) == "wP"
    assert get(board, 1, 0) == "bP"


def test_pawn_captures_diagonally():
    rows = [[".", ".", "."], [".", "bP", "."], ["wP", ".", "."], [".", ".", "."]]
    engine, controller, board = make_engine(rows)
    controller.click(*cell_to_pixel(2, 0))
    controller.click(*cell_to_pixel(1, 1))
    engine.wait(MOVE_DURATION)

    assert get(board, 1, 1) == "wP"
    assert is_empty(board, 2, 0)


def test_cannot_capture_own_color_piece_stays_in_place():
    engine, controller, board = make_engine([["wR", ".", "wP"], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))
    engine.wait(MOVE_DURATION * 2)

    # clicking a friendly piece replaces the selection instead of capturing it
    assert controller.selected == (0, 2)
    assert get(board, 0, 0) == "wR"
    assert get(board, 0, 2) == "wP"


def test_king_capture_ends_the_game():
    rows = [["wR", ".", "bK"], [".", ".", "."], [".", ".", "."]]
    engine, controller, board = make_engine(rows)
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))
    engine.wait(MOVE_DURATION * 2)

    assert engine.game_over is True


def test_click_after_game_over_is_ignored():
    rows = [["wR", ".", "bK"], [".", ".", "."], ["wN", ".", "."]]
    engine, controller, board = make_engine(rows)
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))
    engine.wait(MOVE_DURATION * 2)
    assert engine.game_over is True

    controller.click(*cell_to_pixel(2, 0))  # attempt to select the knight
    assert controller.selected is None

    controller.click(*cell_to_pixel(2, 1))  # attempt to move it
    engine.wait(MOVE_DURATION)

    assert get(board, 2, 0) == "wN"  # untouched: the click never took effect
    assert is_empty(board, 2, 1)


def test_render_still_reflects_final_state_after_game_over():
    rows = [["wR", ".", "bK"], [".", ".", "."], [".", ".", "."]]
    engine, controller, board = make_engine(rows)
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))
    engine.wait(MOVE_DURATION * 2)
    assert engine.game_over is True

    engine.wait(0)
    text = BoardPrinter().render(engine.snapshot())
    assert text == ". . wR\n. . .\n. . ."


def test_injected_win_condition_overrides_default_behaviour():
    rows = [["wR", ".", "bK"], [".", ".", "."], [".", ".", "."]]
    engine, controller, board = make_engine(rows, win_condition=NeverEndsWinCondition())
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))
    engine.wait(MOVE_DURATION * 2)

    assert engine.game_over is False


def test_jump_intercepts_a_move_of_the_opposite_color():
    rows = [["wR", "bP"], [".", "."]]
    engine, controller, board = make_engine(rows)
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 1))
    controller.jump(*cell_to_pixel(0, 1))

    engine.wait(JUMP_DURATION)
    assert get(board, 0, 1) == "bP"  # move was intercepted, target unchanged


def test_jump_does_not_move_the_piece():
    engine, controller, board = make_engine([["bP", "."], [".", "."]])
    controller.jump(*cell_to_pixel(0, 0))

    assert get(board, 0, 0) == "bP"  # still on its own cell, board untouched by the jump itself


def test_intercepted_move_removes_the_arriving_piece_entirely():
    rows = [["wR", "bP"], [".", "."]]
    engine, controller, board = make_engine(rows)
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 1))
    controller.jump(*cell_to_pixel(0, 1))

    engine.wait(JUMP_DURATION)
    assert get(board, 0, 1) == "bP"  # airborne piece remains in its original cell
    assert is_empty(board, 0, 0)  # the arriving piece is removed, not left at its source


def test_jump_lands_normally_and_piece_can_move_again_if_no_interception():
    engine, controller, board = make_engine([["bP", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.jump(*cell_to_pixel(0, 0))
    engine.wait(JUMP_DURATION)  # jump window elapses with no enemy arrival

    controller.click(*cell_to_pixel(0, 0))
    assert controller.selected == (0, 0)  # no longer airborne/busy, selectable again
    controller.click(*cell_to_pixel(1, 0))
    engine.wait(MOVE_DURATION)

    assert get(board, 1, 0) == "bP"
    assert is_empty(board, 0, 0)


def test_moving_piece_cannot_jump():
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))  # rook now mid-move, (0, 0) is busy

    controller.jump(*cell_to_pixel(0, 0))  # rejected: a moving piece cannot jump
    engine.wait(JUMP_DURATION)

    # nothing intercepts the rook's own move; it lands normally
    engine.wait(MOVE_DURATION * 2)
    assert get(board, 0, 2) == "wR"


def test_airborne_piece_cannot_be_selected_or_moved():
    engine, controller, board = make_engine([["bP", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.jump(*cell_to_pixel(0, 0))

    controller.click(*cell_to_pixel(0, 0))
    assert controller.selected is None  # cannot select a piece while it's airborne


def test_jump_on_empty_cell_is_ignored():
    engine, controller, board = make_engine([["wR", "bP", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 1))
    engine.wait(MOVE_DURATION)  # bP is captured; (0, 0) is now empty

    controller.jump(*cell_to_pixel(0, 0))  # a captured piece cannot jump: nothing there
    engine.wait(JUMP_DURATION)
    assert is_empty(board, 0, 0)
    assert get(board, 0, 1) == "wR"  # unaffected


def test_king_intercepted_by_jump_ends_the_game():
    rows = [["wK", ".", "."], ["bP", ".", "."], [".", ".", "."]]
    engine, controller, board = make_engine(rows)
    controller.jump(*cell_to_pixel(1, 0))  # bP jumps in place, guarding (1, 0)
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(1, 0))  # white king walks into the intercept

    engine.wait(MOVE_DURATION)
    assert engine.game_over is True
    assert get(board, 1, 0) == "bP"
    assert is_empty(board, 0, 0)


def test_pawn_promotion_on_arrival():
    # white pawn one step from the last rank (row 0)
    rows = [[".", ".", "."], ["wP", ".", "."], [".", ".", "."]]
    engine, controller, board = make_engine(rows)

    controller.click(*cell_to_pixel(1, 0))
    controller.click(*cell_to_pixel(0, 0))
    engine.wait(MOVE_DURATION)

    assert get(board, 0, 0) == "wQ"


def test_black_pawn_promotes_to_queen_on_arrival():
    # black pawn one step from the last rank (row 2 on a 3-row board)
    rows = [[".", ".", "."], ["bP", ".", "."], [".", ".", "."]]
    engine, controller, board = make_engine(rows)

    controller.click(*cell_to_pixel(1, 0))
    controller.click(*cell_to_pixel(2, 0))
    engine.wait(MOVE_DURATION)

    assert get(board, 2, 0) == "bQ"


def test_pawn_double_step_onto_last_rank_promotes_in_one_motion():
    # white's start row is one row in front of the back rank (height - 2 = 2
    # on this 4-row board); double-stepping from there lands directly on
    # row 0, the promotion rank.
    rows = [[".", ".", "."], [".", ".", "."], ["wP", ".", "."], [".", ".", "."]]
    engine, controller, board = make_engine(rows)

    controller.click(*cell_to_pixel(2, 0))
    controller.click(*cell_to_pixel(0, 0))
    engine.wait(MOVE_DURATION * 2)

    assert get(board, 0, 0) == "wQ"


def test_injected_promotion_rule_overrides_default_behaviour():
    rows = [[".", ".", "."], ["wP", ".", "."], [".", ".", "."]]
    engine, controller, board = make_engine(rows, promotion_rule=NoPromotion())

    controller.click(*cell_to_pixel(1, 0))
    controller.click(*cell_to_pixel(0, 0))
    engine.wait(MOVE_DURATION)

    assert get(board, 0, 0) == "wP"


def test_cannot_select_a_piece_that_is_mid_move():
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))  # move queued, (0, 0) now busy
    assert controller.selected is None

    controller.click(*cell_to_pixel(0, 0))  # try to re-select the moving piece
    assert controller.selected is None


def test_piece_cannot_be_redirected_while_moving():
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))  # original move: (0, 0) -> (0, 2)

    engine.wait(MOVE_DURATION)  # partway through the move
    controller.click(*cell_to_pixel(0, 0))  # attempt to re-select mid-flight
    controller.click(*cell_to_pixel(2, 0))  # attempt to redirect to a new target

    engine.wait(MOVE_DURATION * 2)  # finish out the original move's duration
    assert get(board, 0, 2) == "wR"  # landed at the original target, not the redirect
    assert is_empty(board, 2, 0)


def test_piece_moves_again_immediately_after_arrival_with_no_cooldown():
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))
    engine.wait(MOVE_DURATION * 2)  # first move lands
    assert get(board, 0, 2) == "wR"

    # immediately queue a second move for the same piece, no extra wait beforehand
    controller.click(*cell_to_pixel(0, 2))
    assert controller.selected == (0, 2)  # selectable right away
    controller.click(*cell_to_pixel(2, 2))
    engine.wait(MOVE_DURATION * 2)

    assert get(board, 2, 2) == "wR"
    assert is_empty(board, 0, 2)


def test_cannot_queue_move_while_opposite_color_piece_is_in_flight():
    rows = [["bR", ".", "."], [".", ".", "."], [".", ".", "wR"]]
    engine, controller, board = make_engine(rows)
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))  # black move queued, arrives at t=2000

    engine.wait(500)
    controller.click(*cell_to_pixel(2, 2))  # select white rook
    controller.click(*cell_to_pixel(2, 0))  # attempt: rejected, black still in flight

    assert controller.selected == (2, 2)  # selection is preserved, not cleared
    assert get(board, 2, 2) == "wR"
    assert is_empty(board, 2, 0)


def test_move_becomes_possible_once_opposite_color_move_settles():
    rows = [["bR", ".", "."], [".", ".", "."], [".", ".", "wR"]]
    engine, controller, board = make_engine(rows)
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))  # black move queued, arrives at t=2000

    engine.wait(500)
    controller.click(*cell_to_pixel(2, 2))
    controller.click(*cell_to_pixel(2, 0))  # rejected, black still in flight

    engine.wait(1600)  # total clock 2100: black's move has now settled
    controller.click(*cell_to_pixel(2, 0))  # re-attempt with the same selection
    engine.wait(MOVE_DURATION * 2)

    assert get(board, 2, 0) == "wR"
    assert is_empty(board, 2, 2)


def test_same_color_moves_can_be_in_flight_simultaneously():
    rows = [["wR", ".", "wN"], [".", ".", "."], [".", ".", "."]]
    engine, controller, board = make_engine(rows)
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(2, 0))  # rook: (0,0) -> (2,0)

    controller.click(*cell_to_pixel(0, 2))
    controller.click(*cell_to_pixel(2, 1))  # knight: (0,2) -> (2,1), no gate blocks same color

    engine.wait(MOVE_DURATION * 2)
    assert get(board, 2, 0) == "wR"
    assert get(board, 2, 1) == "wN"


def test_two_friendly_moves_racing_to_the_same_destination_first_queued_wins():
    rows = [["wR", ".", "."], [".", ".", "."], ["wB", ".", "."]]
    engine, controller, board = make_engine(rows)
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))  # rook queued first: (0,0) -> (0,2)

    controller.click(*cell_to_pixel(2, 0))
    controller.click(*cell_to_pixel(0, 2))  # bishop queued second, same destination

    engine.wait(MOVE_DURATION * 2)  # both moves arrive on the same tick

    assert get(board, 0, 2) == "wR"  # first-queued piece wins the cell
    assert get(board, 2, 0) == "wB"  # second piece silently stays put, no duplication/crash


def test_render_returns_current_board_text():
    engine, controller, board = make_engine([["wK", "."], [".", "bK"]])
    engine.wait(0)
    text = BoardPrinter().render(engine.snapshot())
    assert text == "wK .\n. bK"
