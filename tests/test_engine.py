import pytest

from model.board import Board
from model.game_state import MoveResult
from model.piece import AnimationState
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
# Zero by default so the many existing tests that chain actions for the
# same piece without an intervening wait are unaffected; cooldown-specific
# tests pass explicit positive values via make_engine's own kwargs.
LONG_REST_DURATION = 0
SHORT_REST_DURATION = 0
EMPTY_CELL = "."


def get(board, row, col):
    piece = board.piece_at(Position(row, col))
    return EMPTY_CELL if piece is None else piece.color.value + piece.kind.value


def is_empty(board, row, col):
    return board.piece_at(Position(row, col)) is None


def snapshot_piece(engine, piece_id):
    return next(p for p in engine.snapshot().pieces if p.id == piece_id)


class NeverEndsWinCondition(WinCondition):
    """Fake collaborator used to test engine behaviour in isolation,
    injected instead of monkeypatching KingCaptureWinCondition."""

    def is_game_over(self, captured_piece):
        return False


class NoPromotion(PromotionRule):
    def promote(self, piece, row, board_height):
        return piece


class SpyPromotionRule(LastRankPromotion):
    """Wraps the real promotion rule but logs every (token, row) it was
    called with, so tests can assert not just the outcome but how many
    times - and for which piece - promotion was actually evaluated."""

    def __init__(self):
        super().__init__()
        self.calls = []

    def promote(self, piece, row, board_height):
        self.calls.append((piece, row))
        return super().promote(piece, row, board_height)


def make_engine(
    rows,
    win_condition=None,
    promotion_rule=None,
    move_duration=MOVE_DURATION,
    jump_duration=JUMP_DURATION,
    long_rest_duration=LONG_REST_DURATION,
    short_rest_duration=SHORT_REST_DURATION,
):
    board = Board(rows)
    registry = build_default_registry(pawn_direction={"w": -1, "b": 1})
    engine = GameEngine(
        board=board,
        rule_engine=RuleEngine(registry),
        arbiter=RealTimeArbiter(board),
        win_condition=win_condition or KingCaptureWinCondition(),
        promotion_rule=promotion_rule or LastRankPromotion(),
        move_duration=move_duration,
        jump_duration=jump_duration,
        long_rest_duration=long_rest_duration,
        short_rest_duration=short_rest_duration,
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


def test_click_on_illegal_target_for_the_selected_piece_cancels_selection():
    engine, controller, board = make_engine([["wR", ".", "."], ["wB", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))  # rook move queued, (0, 0) now empty
    assert controller.selected is None

    controller.click(*cell_to_pixel(1, 0))  # select the bishop
    assert controller.selected == (1, 0)

    controller.click(*cell_to_pixel(0, 0))  # not diagonal: illegal for a bishop
    assert controller.selected is None  # selection cancelled, not kept


def test_selecting_then_moving_starts_a_move():
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    piece_id = board.piece_at(Position(0, 0)).id
    controller.click(*cell_to_pixel(0, 2))

    assert controller.selected is None
    # The piece leaves the source cell the instant the motion is queued -
    # it travels as part of the Motion, not as a Board occupant - so the
    # source reads as empty immediately, not "still there until it lands".
    assert is_empty(board, 0, 0)
    assert is_empty(board, 0, 2)
    # It still exists and renders at its source until it actually lands.
    snap = snapshot_piece(engine, piece_id)
    assert (snap.row, snap.col) == (0, 0)


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
    assert is_empty(board, 0, 0)  # already gone from its old cell
    assert is_empty(board, 0, 2)  # not landed yet either - still in flight


def test_wait_calls_accumulate_toward_arrival_time():
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    piece_id = board.piece_at(Position(0, 0)).id
    controller.click(*cell_to_pixel(0, 2))

    engine.wait(MOVE_DURATION)  # halfway there: in flight, on neither cell
    assert is_empty(board, 0, 0)
    assert is_empty(board, 0, 2)
    assert snapshot_piece(engine, piece_id).render_col == 1.0  # halfway between col 0 and col 2

    engine.wait(MOVE_DURATION)  # the rest of the duration: now it lands
    assert get(board, 0, 2) == "wR"
    assert is_empty(board, 0, 0)


def test_illegal_move_cancels_selection_and_leaves_piece_in_place():
    engine, controller, board = make_engine([["wN", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 1))  # not a legal knight move

    assert controller.selected is None  # selection is cancelled, not kept open
    assert get(board, 0, 0) == "wN"  # the piece itself never moved

    controller.click(*cell_to_pixel(0, 0))  # must be selected again from scratch
    assert controller.selected == (0, 0)


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

    assert controller.selected is None  # illegal target cancels the selection
    assert get(board, 0, 0) == "wK"


def test_rook_illegal_diagonal_move_is_ignored():
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(2, 2))  # diagonal: illegal for a rook
    engine.wait(MOVE_DURATION * 2)

    assert controller.selected is None  # illegal target cancels the selection
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

    assert controller.selected is None  # illegal target cancels the selection
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

    assert controller.selected is None  # illegal target cancels the selection
    assert get(board, 0, 0) == "wR"
    assert get(board, 0, 1) == "bP"


def test_bishop_blocked_by_piece_is_ignored():
    engine, controller, board = make_engine([["wB", ".", "."], [".", "bP", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(2, 2))  # blocked by the piece at (1, 1)
    engine.wait(MOVE_DURATION * 2)

    assert controller.selected is None  # illegal target cancels the selection
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

    assert controller.selected is None  # illegal target cancels the selection
    assert get(board, 3, 0) == "wP"


def test_pawn_cannot_capture_forward():
    rows = [[".", ".", "."], ["bP", ".", "."], ["wP", ".", "."], [".", ".", "."]]
    engine, controller, board = make_engine(rows)
    controller.click(*cell_to_pixel(2, 0))
    controller.click(*cell_to_pixel(1, 0))
    engine.wait(MOVE_DURATION)

    assert controller.selected is None  # illegal target cancels the selection
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


def test_request_move_rejects_a_source_under_an_active_jump():
    # Controller._is_busy() already blocks re-selecting a jump-guarding
    # piece, but GameEngine.request_move() is a public method a caller
    # could invoke directly (bypassing Controller). Without its own guard,
    # the guarding piece could move away, leaving its jump "orphaned" on a
    # now-empty (or later reoccupied) cell.
    rows = [["bR", ".", "."]]
    engine, controller, board = make_engine(rows)
    controller.jump(*cell_to_pixel(0, 0))
    assert engine.arbiter.is_jumping_on(Position(0, 0))

    result = engine.request_move(Position(0, 0), Position(0, 1))

    assert result == MoveResult(False, "jump_in_progress")
    assert get(board, 0, 0) == "bR"  # the guarding piece never left
    assert engine.arbiter.is_jumping_on(Position(0, 0))  # the guard is still intact


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


def test_request_jump_directly_starts_a_jump():
    engine, controller, board = make_engine([["wR", "bP"], [".", "."]])
    engine.request_jump(Position(0, 0))
    assert engine.is_position_busy(Position(0, 0)) is True


def test_request_jump_on_empty_cell_is_ignored():
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    engine.request_jump(Position(0, 1))
    assert engine.is_position_busy(Position(0, 1)) is False


def test_request_jump_on_busy_cell_is_ignored():
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    engine.request_move(Position(0, 0), Position(0, 2))  # rook now mid-move, (0, 0) is busy

    engine.request_jump(Position(0, 0))
    engine.wait(JUMP_DURATION)

    # nothing intercepts the rook's own move; it lands normally
    engine.wait(MOVE_DURATION * 2)
    assert get(board, 0, 2) == "wR"


def test_is_position_busy_is_not_set_by_a_departed_motions_old_cell():
    # A piece leaves its cell the instant its own motion starts (see
    # RealTimeArbiter.start_motion) - the now-empty source isn't "busy"
    # in any sense that should stop something else from being selected
    # or jump-guarded there; is_position_busy only reflects an active
    # jump (see test_is_position_busy_reflects_active_jump).
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    assert engine.is_position_busy(Position(0, 0)) is False

    engine.request_move(Position(0, 0), Position(0, 2))
    assert engine.is_position_busy(Position(0, 0)) is False


def test_is_position_busy_reflects_active_jump():
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    assert engine.is_position_busy(Position(0, 0)) is False

    engine.request_jump(Position(0, 0))
    assert engine.is_position_busy(Position(0, 0)) is True


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


def test_promote_called_once_for_the_piece_that_actually_landed():
    # Two enemy motions converge on the same destination with different
    # arrival times: wR (1,0)->(0,0), distance 1, lands first on an empty
    # cell (no capture); bN (2,1)->(0,0) is a legal knight move (distance
    # 2 for duration purposes, whatever the actual geometry), arriving
    # later and capturing wR normally once it's actually there. Guards
    # the same thing the identity check in _apply_events
    # (moved.id != event.piece_id) is for: promote() must be attributed
    # to the piece that truly ended up at the destination, not re-derived
    # from stale board state.
    rows = [[".", ".", "."], ["wR", ".", "."], [".", "bN", "."]]
    spy = SpyPromotionRule()
    engine, controller, board = make_engine(rows, promotion_rule=spy)

    controller.click(*cell_to_pixel(1, 0))
    controller.click(*cell_to_pixel(0, 0))  # wR queued first: (1,0) -> (0,0), distance 1
    controller.click(*cell_to_pixel(2, 1))
    controller.click(*cell_to_pixel(0, 0))  # bN queued second, same destination, distance 2

    engine.wait(MOVE_DURATION)  # wR lands first (empty cell, no capture)
    assert get(board, 0, 0) == "wR"

    engine.wait(MOVE_DURATION)  # bN now arrives too, capturing wR for real
    assert get(board, 0, 0) == "bN"
    # One call for wR's own (uneventful) landing, one for bN's landing/
    # capture - each correctly attributed to the piece that arrived in
    # that specific event, never misattributed to whatever the other one
    # subsequently overwrote the cell with.
    assert spy.calls == [("wR", 0), ("bN", 0)]


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
    # Relies on make_engine's zero-duration rest defaults (see
    # LONG_REST_DURATION/SHORT_REST_DURATION above) - with a real,
    # positive cooldown configured, this same sequence would be rejected
    # instead; see test_piece_cannot_move_again_while_resting_after_a_move.
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


def test_piece_cannot_move_again_while_resting_after_a_move():
    rows = [["wR", ".", "."], [".", ".", "."], [".", ".", "."]]
    engine, controller, board = make_engine(rows, long_rest_duration=500)

    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))
    engine.wait(MOVE_DURATION * 2)  # lands; long-rest cooldown starts now
    assert get(board, 0, 2) == "wR"

    result = engine.request_move(Position(0, 2), Position(2, 2))
    assert result == MoveResult(False, "resting")
    assert get(board, 0, 2) == "wR"  # never left

    engine.wait(500)  # cooldown elapses
    result = engine.request_move(Position(0, 2), Position(2, 2))
    assert result.is_accepted


def test_piece_cannot_jump_while_resting_after_a_move():
    rows = [["wR", ".", "."], [".", ".", "."], [".", ".", "."]]
    engine, controller, board = make_engine(rows, long_rest_duration=500)

    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))
    engine.wait(MOVE_DURATION * 2)

    engine.request_jump(Position(0, 2))
    assert not engine.arbiter.is_jumping_on(Position(0, 2))  # rejected, still resting

    engine.wait(500)
    engine.request_jump(Position(0, 2))
    assert engine.arbiter.is_jumping_on(Position(0, 2))


def test_piece_rests_after_a_jump_ends_and_can_act_again_once_it_elapses():
    rows = [["wR", ".", "."], [".", ".", "."], [".", ".", "."]]
    engine, controller, board = make_engine(rows, short_rest_duration=300)

    engine.request_jump(Position(0, 0))
    engine.wait(JUMP_DURATION)  # jump window ends; short-rest cooldown starts now

    result = engine.request_move(Position(0, 0), Position(0, 1))
    assert result == MoveResult(False, "resting")

    engine.wait(300)  # cooldown elapses
    result = engine.request_move(Position(0, 0), Position(0, 1))
    assert result.is_accepted


def test_cooldown_only_starts_once_a_piece_truly_lands_not_at_a_mid_flight_capture():
    # Reuses the crossing-paths shape already proven correct in
    # RealTimeArbiter's own collision tests: black crosses white's path
    # and captures it mid-flight, then continues to its own real
    # destination. The long-rest cooldown must only start once black
    # actually lands there - not at the earlier instant it captured
    # white in passing (see GameEngine._apply_events' reuse of the
    # "did it truly land here" identity check for exactly this).
    rows = [
        [".", ".", "bR", ".", "."],
        [".", ".", ".", ".", "."],
        ["wR", ".", ".", ".", "."],
        [".", ".", ".", ".", "."],
        [".", ".", ".", ".", "."],
    ]
    engine, controller, board = make_engine(rows, move_duration=100, long_rest_duration=50)
    black_id = board.piece_at(Position(0, 2)).id

    engine.request_move(Position(2, 0), Position(2, 4))  # white: crosses col 2 at t=200
    engine.wait(50)
    engine.request_move(Position(0, 2), Position(4, 2))  # black: crosses row 2 at t=50+200=250

    engine.wait(200)  # clock now 250: the crossing collision resolves this instant
    assert not engine.arbiter.is_resting(black_id)  # still flying to its own destination

    engine.wait(200)  # clock now 450: black lands for real
    assert get(board, 4, 2) == "bR"
    assert engine.arbiter.is_resting(black_id)  # now resting - cooldown just started

    engine.wait(50)  # its 50ms cooldown elapses
    assert not engine.arbiter.is_resting(black_id)


def test_opposite_color_moves_can_be_in_flight_simultaneously():
    rows = [["bR", ".", "."], [".", ".", "."], [".", ".", "wR"]]
    engine, controller, board = make_engine(rows)
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))  # black rook: (0,0) -> (0,2)

    controller.click(*cell_to_pixel(2, 2))
    controller.click(*cell_to_pixel(2, 0))  # white rook: (2,2) -> (2,0), no gate blocks opposite color

    engine.wait(MOVE_DURATION * 2)
    assert get(board, 0, 2) == "bR"
    assert get(board, 2, 0) == "wR"


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


def test_two_friendly_moves_with_an_exact_arrival_tie_both_stop_short():
    # Rook and bishop, same color, queued back to back (t=0) with equal
    # distance (2) to the same destination - an exact simultaneous
    # meeting, not "whoever was queued first". Per the documented tie
    # policy (see RealTimeArbiter._resolve_collision), there's no
    # well-defined first/second for an exact tie between friendlies:
    # neither reaches the contested cell, both stop one cell short along
    # their own path instead.
    rows = [["wR", ".", "."], [".", ".", "."], ["wB", ".", "."]]
    engine, controller, board = make_engine(rows)
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))  # rook: (0,0) -> (0,2), distance 2

    controller.click(*cell_to_pixel(2, 0))
    controller.click(*cell_to_pixel(0, 2))  # bishop: (2,0) -> (0,2), distance 2 (diagonal) - exact tie

    engine.wait(MOVE_DURATION * 2)  # both would arrive at the exact same instant

    assert is_empty(board, 0, 2)  # neither reaches the contested cell
    assert get(board, 0, 1) == "wR"  # rook stopped one cell short, along its own path
    assert get(board, 1, 1) == "wB"  # bishop stopped one cell short, along its own path


def test_two_friendly_motions_racing_non_tied_first_continues_second_stops_short():
    # Two same-color rooks moving along the same row toward the same
    # destination, queued at the same time but with different distances
    # to travel - so they reach their first shared cell at genuinely
    # different times, not an exact tie (see the test above for that).
    rows = [["wR", "wR", ".", "."]]
    engine, controller, board = make_engine(rows)

    controller.click(*cell_to_pixel(0, 1))
    controller.click(*cell_to_pixel(0, 3))  # short rook: (0,1) -> (0,3), distance 2

    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 3))  # long rook: (0,0) -> (0,3), distance 3, same destination

    engine.wait(MOVE_DURATION * 2)

    assert get(board, 0, 3) == "wR"  # the short rook reached its own original destination
    assert get(board, 0, 1) == "wR"  # the long rook stopped one cell short of their first shared cell
    assert is_empty(board, 0, 2)  # neither piece is sitting at the contested crossing cell


def test_same_color_piece_cannot_enter_a_teammates_departure_cell():
    rows = [["wR", ".", "."], [".", ".", "."], [".", "wN", "."]]
    engine, controller, board = make_engine(rows)

    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))  # wR departs (0, 0), heading elsewhere
    assert is_empty(board, 0, 0)

    result = engine.request_move(Position(2, 1), Position(0, 0))  # wN: same color, targets the vacated cell
    assert result == MoveResult(False, "friendly_departure_cell")
    assert is_empty(board, 0, 0)  # nothing moved there


def test_enemy_piece_can_enter_a_departing_pieces_source_cell():
    rows = [["wR", ".", "."], [".", ".", "."], [".", "bN", "."]]
    engine, controller, board = make_engine(rows)

    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))  # wR departs (0, 0)
    assert is_empty(board, 0, 0)

    result = engine.request_move(Position(2, 1), Position(0, 0))  # bN: enemy, same target cell
    assert result.is_accepted


def test_render_returns_current_board_text():
    engine, controller, board = make_engine([["wK", "."], [".", "bK"]])
    engine.wait(0)
    text = BoardPrinter().render(engine.snapshot())
    assert text == "wK .\n. bK"


# -- wait(0): GameEngine.wait(0)/RealTimeArbiter.advance_time(0) never
# advances the clock, but can still resolve a motion/jump that's already
# due. Controller.click()/jump() used to call wait(0) defensively before
# acting, because GameEngine.__init__ once accepted a move_duration/
# jump_duration of 0, under which a motion could be immediately due the
# instant it was queued. Now that construction rejects non-positive
# durations (see test_construction_rejects_* below), a validated move
# always covers distance >= 1 and jump_duration is always positive, so a
# motion/jump can never be due the instant it's created; combined with
# RealTimeArbiter.advance_time() always fully draining whatever's overdue
# before it returns, nothing can ever be sitting "already due but
# unresolved" when Controller.click()/jump() runs. That made the wait(0)
# calls there unconditionally redundant, so they were removed. The tests
# below cover wait(0)/advance_time(0) as general GameEngine/RealTimeArbiter
# behaviour (still relevant - e.g. ScriptRunner calls wait(0) before
# rendering), and test_wait_zero_is_always_a_noop_for_a_real_motion proves
# the specific invariant that justified the removal.


def test_wait_zero_does_not_advance_clock():
    engine, controller, board = make_engine([["wK", "."], [".", "."]])
    engine.wait(500)
    clock_before = engine.clock
    engine.wait(0)
    assert engine.clock == clock_before


def test_wait_zero_is_noop_when_nothing_pending():
    engine, controller, board = make_engine([["wR", ".", "."]])
    events = engine.arbiter.advance_time(0)
    assert events == []
    assert engine.arbiter.clock == 0
    assert get(board, 0, 0) == "wR"


def test_wait_zero_is_always_a_noop_for_a_real_motion():
    # Because GameEngine now guarantees move_duration/jump_duration > 0
    # (test_construction_rejects_* below), a queued motion's arrival_time
    # is always strictly in the future relative to the clock at queue
    # time - it can never be immediately due. wait(0) right after queuing
    # therefore resolves nothing, and wait(0) right after the motion has
    # already landed (via a real wait()) also resolves nothing further,
    # since advance_time() always fully drains what's overdue on its own.
    # This is the invariant that made Controller.click()/jump()'s wait(0)
    # calls unconditionally redundant.
    engine, controller, board = make_engine([["wR", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))  # queue a real, positive-duration move

    assert engine.arbiter.advance_time(0) == []  # not due yet - can't be

    engine.wait(MOVE_DURATION * 2)  # let it land normally
    assert engine.arbiter.advance_time(0) == []  # already resolved, nothing left


def test_stale_selection_after_capture_is_not_acted_on():
    # The selected piece can be captured - and its cell taken by a
    # different piece - while it sits waiting for a second click. This
    # exercises that scenario through pure Controller clicks (both colors
    # driven by the same Controller, as other tests here already do).
    rows = [["wQ", ".", "."], [".", ".", "."], ["bR", ".", "."]]
    engine, controller, board = make_engine(rows)

    controller.click(*cell_to_pixel(2, 0))  # select bR
    controller.click(*cell_to_pixel(0, 0))  # queue bR: (2,0) -> (0,0)
    assert controller.selected is None

    controller.click(*cell_to_pixel(0, 0))  # select wQ, still sitting there
    assert controller.selected == (0, 0)

    engine.wait(MOVE_DURATION * 2)  # bR arrives, capturing wQ
    assert get(board, 0, 0) == "bR"

    controller.click(*cell_to_pixel(0, 1))  # attempt to move the (now-gone) wQ
    assert controller.selected is None  # stale selection discarded, not acted on


def test_piece_continues_to_destination_after_enemy_moves_into_vacated_source():
    # wR queues a long (2-square) move away from (2,0) - the source is
    # free immediately (a piece leaves the instant its own motion
    # starts, see RealTimeArbiter.start_motion), so an *enemy* piece can
    # legally move into it. That's a normal move into empty space, not a
    # capture (wR isn't there to capture) - and it has no effect on wR's
    # own motion, which keeps travelling to its original destination.
    rows = [[".", ".", "."], [".", "bB", "."], ["wR", ".", "."]]
    engine, controller, board = make_engine(rows)

    controller.click(*cell_to_pixel(2, 0))
    controller.click(*cell_to_pixel(0, 0))  # wR: (2,0) -> (0,0), distance 2 (long)
    assert is_empty(board, 2, 0)  # source is free immediately

    controller.click(*cell_to_pixel(1, 1))
    controller.click(*cell_to_pixel(2, 0))  # bB: (1,1) -> (2,0), a normal move into empty space

    engine.wait(MOVE_DURATION)  # bB lands (distance 1); wR is still en route (distance 2)
    assert get(board, 2, 0) == "bB"  # landed normally - nothing was there to capture

    controller.click(*cell_to_pixel(2, 0))  # bB is idle and immediately selectable
    assert controller.selected == (2, 0)

    engine.wait(MOVE_DURATION)  # wR's own motion (distance 2) now completes
    assert get(board, 0, 0) == "wR"  # wR reached its original destination, unaffected


def test_construction_accepts_positive_durations():
    make_engine([["wK", "."], [".", "."]], move_duration=1000, jump_duration=1000)


def test_construction_rejects_zero_move_duration():
    with pytest.raises(ValueError):
        make_engine([["wK", "."], [".", "."]], move_duration=0, jump_duration=1000)


def test_construction_rejects_negative_move_duration():
    with pytest.raises(ValueError):
        make_engine([["wK", "."], [".", "."]], move_duration=-1, jump_duration=1000)


def test_construction_rejects_zero_jump_duration():
    with pytest.raises(ValueError):
        make_engine([["wK", "."], [".", "."]], move_duration=1000, jump_duration=0)


def test_construction_rejects_negative_jump_duration():
    with pytest.raises(ValueError):
        make_engine([["wK", "."], [".", "."]], move_duration=1000, jump_duration=-100)


def test_construction_accepts_zero_rest_durations():
    # Unlike move/jump duration, 0 is a legitimate "no cooldown" value
    # for rest durations - see GameEngine.__init__'s own comment.
    make_engine([["wK", "."], [".", "."]], long_rest_duration=0, short_rest_duration=0)


def test_construction_rejects_negative_long_rest_duration():
    with pytest.raises(ValueError):
        make_engine([["wK", "."], [".", "."]], long_rest_duration=-1)


def test_construction_rejects_negative_short_rest_duration():
    with pytest.raises(ValueError):
        make_engine([["wK", "."], [".", "."]], short_rest_duration=-1)


def test_snapshot_render_position_matches_source_right_after_queuing_a_move():
    rows = [["wR", ".", "."]]
    engine, controller, board = make_engine(rows)
    piece_id = board.piece_at(Position(0, 0)).id

    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))  # queue (0,0) -> (0,2), distance 2

    snap = snapshot_piece(engine, piece_id)
    assert (snap.row, snap.col) == (0, 0)  # logical position unchanged until arrival
    assert (snap.render_row, snap.render_col) == (0.0, 0.0)
    assert snap.animation_state == AnimationState.MOVE


def test_snapshot_render_position_interpolates_midway_through_a_move():
    rows = [["wR", ".", "."]]
    engine, controller, board = make_engine(rows)
    piece_id = board.piece_at(Position(0, 0)).id

    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))  # distance 2 -> duration = 2 * MOVE_DURATION

    engine.wait(MOVE_DURATION)  # exactly halfway (progress = 0.5)

    snap = snapshot_piece(engine, piece_id)
    assert (snap.row, snap.col) == (0, 0)  # still logically at the source
    assert snap.render_row == 0.0
    assert snap.render_col == 1.0  # halfway between col 0 and col 2
    assert snap.animation_state == AnimationState.MOVE


def test_snapshot_render_position_matches_destination_after_arrival():
    rows = [["wR", ".", "."]]
    engine, controller, board = make_engine(rows)
    piece_id = board.piece_at(Position(0, 0)).id

    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))
    engine.wait(MOVE_DURATION * 2)  # fully lands

    snap = snapshot_piece(engine, piece_id)
    assert (snap.row, snap.col) == (0, 2)
    assert (snap.render_row, snap.render_col) == (0.0, 2.0)
    assert snap.animation_state == AnimationState.IDLE


def test_snapshot_animation_state_is_jump_while_jump_active():
    rows = [["bP", "."]]
    engine, controller, board = make_engine(rows)
    piece_id = board.piece_at(Position(0, 0)).id

    controller.jump(*cell_to_pixel(0, 0))

    snap = snapshot_piece(engine, piece_id)
    assert snap.animation_state == AnimationState.JUMP
    assert (snap.render_row, snap.render_col) == (0.0, 0.0)  # jumping doesn't move the piece


def test_snapshot_animation_state_is_idle_by_default():
    rows = [["wK", "."]]
    engine, controller, board = make_engine(rows)
    piece_id = board.piece_at(Position(0, 0)).id

    snap = snapshot_piece(engine, piece_id)
    assert snap.animation_state == AnimationState.IDLE
    assert (snap.render_row, snap.render_col) == (0.0, 0.0)
