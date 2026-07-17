import pytest

from model.board import Board
from model.game_state import ActionResult, ActionResultReason
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
# 0 by default so tests that chain actions for the same piece without an
# intervening wait are unaffected; cooldown-specific tests pass explicit
# positive values via make_engine's own kwargs.
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
    def is_game_over(self, captured_piece):
        return False


class NoPromotion(PromotionRule):
    def promote(self, piece, row, board_height):
        return piece


class SpyPromotionRule(LastRankPromotion):
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
    engine, controller, board = make_engine([["wR", "wQ", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(50, 50)
    assert controller.selected == (0, 0)
    controller.click(150, 50)
    assert controller.selected == (0, 1)
    assert get(board, 0, 0) == "wR"
    assert get(board, 0, 1) == "wQ"


def test_click_friendly_piece_replaces_selection():
    engine, controller, board = make_engine([["wR", "wQ", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    assert controller.selected == (0, 0)

    controller.click(*cell_to_pixel(0, 1))
    assert controller.selected == (0, 1)
    assert get(board, 0, 0) == "wR"
    assert get(board, 0, 1) == "wQ"


def test_click_on_illegal_target_for_the_selected_piece_cancels_selection():
    engine, controller, board = make_engine([["wR", ".", "."], ["wB", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))
    assert controller.selected is None

    controller.click(*cell_to_pixel(1, 0))
    assert controller.selected == (1, 0)

    controller.click(*cell_to_pixel(0, 0))
    assert controller.selected is None


def test_selecting_then_moving_starts_a_move():
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    piece_id = board.piece_at(Position(0, 0)).id
    controller.click(*cell_to_pixel(0, 2))

    assert controller.selected is None
    assert is_empty(board, 0, 0)
    assert is_empty(board, 0, 2)
    snap = snapshot_piece(engine, piece_id)
    assert (snap.row, snap.col) == (0, 0)


def test_move_lands_after_move_duration_elapses():
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))

    engine.wait(MOVE_DURATION * 2)
    assert get(board, 0, 2) == "wR"
    assert is_empty(board, 0, 0)


def test_move_does_not_land_before_duration_fully_elapses():
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))

    engine.wait(MOVE_DURATION * 2 - 1)
    assert is_empty(board, 0, 0)
    assert is_empty(board, 0, 2)


def test_wait_calls_accumulate_toward_arrival_time():
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    piece_id = board.piece_at(Position(0, 0)).id
    controller.click(*cell_to_pixel(0, 2))

    engine.wait(MOVE_DURATION)
    assert is_empty(board, 0, 0)
    assert is_empty(board, 0, 2)
    assert snapshot_piece(engine, piece_id).render_col == 1.0

    engine.wait(MOVE_DURATION)
    assert get(board, 0, 2) == "wR"
    assert is_empty(board, 0, 0)


def test_illegal_move_cancels_selection_and_leaves_piece_in_place():
    engine, controller, board = make_engine([["wN", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 1))

    assert controller.selected is None
    assert get(board, 0, 0) == "wN"

    controller.click(*cell_to_pixel(0, 0))
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
    controller.click(*cell_to_pixel(2, 0))
    engine.wait(MOVE_DURATION * 2)

    assert controller.selected is None
    assert get(board, 0, 0) == "wK"


def test_rook_illegal_diagonal_move_is_ignored():
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(2, 2))
    engine.wait(MOVE_DURATION * 2)

    assert controller.selected is None
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
    controller.click(*cell_to_pixel(0, 2))
    engine.wait(MOVE_DURATION * 2)

    assert controller.selected is None
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
    controller.click(*cell_to_pixel(0, 2))
    engine.wait(MOVE_DURATION * 2)

    assert controller.selected is None
    assert get(board, 0, 0) == "wR"
    assert get(board, 0, 1) == "bP"


def test_bishop_blocked_by_piece_is_ignored():
    engine, controller, board = make_engine([["wB", ".", "."], [".", "bP", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(2, 2))
    engine.wait(MOVE_DURATION * 2)

    assert controller.selected is None
    assert get(board, 0, 0) == "wB"
    assert get(board, 1, 1) == "bP"


def test_knight_jumps_over_blockers_and_lands():
    engine, controller, board = make_engine([["wN", "wP", "."], ["wP", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(2, 1))
    engine.wait(MOVE_DURATION * 2)

    assert get(board, 2, 1) == "wN"
    assert is_empty(board, 0, 0)
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
    rows = [[".", ".", "."], [".", ".", "."], [".", ".", "."], ["wP", ".", "."]]
    engine, controller, board = make_engine(rows)
    controller.click(*cell_to_pixel(3, 0))
    controller.click(*cell_to_pixel(1, 0))
    engine.wait(MOVE_DURATION * 2)

    assert controller.selected is None
    assert get(board, 3, 0) == "wP"


def test_pawn_cannot_capture_forward():
    rows = [[".", ".", "."], ["bP", ".", "."], ["wP", ".", "."], [".", ".", "."]]
    engine, controller, board = make_engine(rows)
    controller.click(*cell_to_pixel(2, 0))
    controller.click(*cell_to_pixel(1, 0))
    engine.wait(MOVE_DURATION)

    assert controller.selected is None
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

    controller.click(*cell_to_pixel(2, 0))
    assert controller.selected is None

    controller.click(*cell_to_pixel(2, 1))
    engine.wait(MOVE_DURATION)

    assert get(board, 2, 0) == "wN"
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
    assert get(board, 0, 1) == "bP"


def test_jump_does_not_move_the_piece():
    engine, controller, board = make_engine([["bP", "."], [".", "."]])
    controller.jump(*cell_to_pixel(0, 0))

    assert get(board, 0, 0) == "bP"


def test_request_move_rejects_a_source_under_an_active_jump():
    rows = [["bR", ".", "."]]
    engine, controller, board = make_engine(rows)
    controller.jump(*cell_to_pixel(0, 0))
    assert engine.arbiter.is_jumping_on(Position(0, 0))

    result = engine.request_move(Position(0, 0), Position(0, 1))

    assert result == ActionResult(False, ActionResultReason.JUMP_IN_PROGRESS)
    assert get(board, 0, 0) == "bR"
    assert engine.arbiter.is_jumping_on(Position(0, 0))


def test_intercepted_move_removes_the_arriving_piece_entirely():
    rows = [["wR", "bP"], [".", "."]]
    engine, controller, board = make_engine(rows)
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 1))
    controller.jump(*cell_to_pixel(0, 1))

    engine.wait(JUMP_DURATION)
    assert get(board, 0, 1) == "bP"
    assert is_empty(board, 0, 0)


def test_jump_lands_normally_and_piece_can_move_again_if_no_interception():
    engine, controller, board = make_engine([["bP", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.jump(*cell_to_pixel(0, 0))
    engine.wait(JUMP_DURATION)

    controller.click(*cell_to_pixel(0, 0))
    assert controller.selected == (0, 0)
    controller.click(*cell_to_pixel(1, 0))
    engine.wait(MOVE_DURATION)

    assert get(board, 1, 0) == "bP"
    assert is_empty(board, 0, 0)


def test_moving_piece_cannot_jump():
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))

    controller.jump(*cell_to_pixel(0, 0))
    engine.wait(JUMP_DURATION)

    engine.wait(MOVE_DURATION * 2)
    assert get(board, 0, 2) == "wR"


def test_airborne_piece_cannot_be_selected_or_moved():
    engine, controller, board = make_engine([["bP", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.jump(*cell_to_pixel(0, 0))

    controller.click(*cell_to_pixel(0, 0))
    assert controller.selected is None


def test_jump_on_empty_cell_is_ignored():
    engine, controller, board = make_engine([["wR", "bP", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 1))
    engine.wait(MOVE_DURATION)

    controller.jump(*cell_to_pixel(0, 0))
    engine.wait(JUMP_DURATION)
    assert is_empty(board, 0, 0)
    assert get(board, 0, 1) == "wR"


def test_jump_clears_a_pending_selection_even_when_targeting_a_different_colored_piece():
    # A single shared Controller has no per-color isolation, so a jump
    # anywhere - even on the opposing color's piece - clears whatever
    # selection is currently pending, same as jumping on its own piece.
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], ["bR", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    assert controller.selected == (0, 0)

    controller.jump(*cell_to_pixel(2, 0))

    assert controller.selected is None


def test_jump_clears_a_pending_selection_even_on_an_empty_cell():
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    assert controller.selected == (0, 0)

    controller.jump(*cell_to_pixel(1, 1))

    assert controller.selected is None


def test_king_intercepted_by_jump_ends_the_game():
    rows = [["wK", ".", "."], ["bP", ".", "."], [".", ".", "."]]
    engine, controller, board = make_engine(rows)
    controller.jump(*cell_to_pixel(1, 0))
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(1, 0))

    engine.wait(MOVE_DURATION)
    assert engine.game_over is True
    assert get(board, 1, 0) == "bP"
    assert is_empty(board, 0, 0)


def test_request_jump_directly_starts_a_jump():
    engine, controller, board = make_engine([["wR", "bP"], [".", "."]])
    engine.request_jump(Position(0, 0))
    assert engine.is_busy(Position(0, 0)) is True


def test_request_jump_on_empty_cell_is_ignored():
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    engine.request_jump(Position(0, 1))
    assert engine.is_busy(Position(0, 1)) is False


def test_request_jump_on_busy_cell_is_ignored():
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    engine.request_move(Position(0, 0), Position(0, 2))

    engine.request_jump(Position(0, 0))
    engine.wait(JUMP_DURATION)

    engine.wait(MOVE_DURATION * 2)
    assert get(board, 0, 2) == "wR"


def test_is_busy_is_not_set_by_a_departed_motions_old_cell():
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    assert engine.is_busy(Position(0, 0)) is False

    engine.request_move(Position(0, 0), Position(0, 2))
    assert engine.is_busy(Position(0, 0)) is False


def test_is_busy_reflects_active_jump():
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    assert engine.is_busy(Position(0, 0)) is False

    engine.request_jump(Position(0, 0))
    assert engine.is_busy(Position(0, 0)) is True


# -- request_move/request_jump always return an ActionResult -----------------


def test_request_jump_on_a_piece_returns_an_accepted_action_result():
    engine, controller, board = make_engine([["wR", "."]])
    result = engine.request_jump(Position(0, 0))
    assert result == ActionResult(True, ActionResultReason.OK)


def test_request_jump_on_an_empty_cell_returns_empty_source():
    engine, controller, board = make_engine([["wR", "."]])
    result = engine.request_jump(Position(0, 1))
    assert result == ActionResult(False, ActionResultReason.EMPTY_SOURCE)


def test_request_jump_on_a_cell_already_jump_guarded_returns_jump_in_progress():
    engine, controller, board = make_engine([["wR", "."]])
    engine.request_jump(Position(0, 0))
    result = engine.request_jump(Position(0, 0))
    assert result == ActionResult(False, ActionResultReason.JUMP_IN_PROGRESS)


def test_request_jump_while_resting_returns_resting():
    engine, controller, board = make_engine([["wR", "."]], short_rest_duration=300)
    engine.request_jump(Position(0, 0))
    engine.wait(JUMP_DURATION)

    result = engine.request_jump(Position(0, 0))

    assert result == ActionResult(False, ActionResultReason.RESTING)


def test_request_jump_after_game_over_returns_game_over():
    rows = [["wR", ".", "bK"], [".", ".", "."], ["wN", ".", "."]]
    engine, controller, board = make_engine(rows)
    engine.request_move(Position(0, 0), Position(0, 2))
    engine.wait(MOVE_DURATION * 2)
    assert engine.game_over is True

    result = engine.request_jump(Position(2, 0))

    assert result == ActionResult(False, ActionResultReason.GAME_OVER)


def test_request_move_after_game_over_returns_game_over():
    rows = [["wR", ".", "bK"], [".", ".", "."], ["wN", ".", "."]]
    engine, controller, board = make_engine(rows)
    engine.request_move(Position(0, 0), Position(0, 2))
    engine.wait(MOVE_DURATION * 2)
    assert engine.game_over is True

    result = engine.request_move(Position(2, 0), Position(2, 1))

    assert result == ActionResult(False, ActionResultReason.GAME_OVER)


def test_pawn_promotion_on_arrival():
    rows = [[".", ".", "."], ["wP", ".", "."], [".", ".", "."]]
    engine, controller, board = make_engine(rows)

    controller.click(*cell_to_pixel(1, 0))
    controller.click(*cell_to_pixel(0, 0))
    engine.wait(MOVE_DURATION)

    assert get(board, 0, 0) == "wQ"


def test_black_pawn_promotes_to_queen_on_arrival():
    rows = [[".", ".", "."], ["bP", ".", "."], [".", ".", "."]]
    engine, controller, board = make_engine(rows)

    controller.click(*cell_to_pixel(1, 0))
    controller.click(*cell_to_pixel(2, 0))
    engine.wait(MOVE_DURATION)

    assert get(board, 2, 0) == "bQ"


def test_pawn_double_step_onto_last_rank_promotes_in_one_motion():
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
    # Two enemy motions converge on the same destination at different
    # arrival times - promote() must be attributed to whichever piece
    # truly ended up there, not re-derived from stale board state (see
    # GameEngine._apply_events' identity check).
    rows = [[".", ".", "."], ["wR", ".", "."], [".", "bN", "."]]
    spy = SpyPromotionRule()
    engine, controller, board = make_engine(rows, promotion_rule=spy)

    controller.click(*cell_to_pixel(1, 0))
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(2, 1))
    controller.click(*cell_to_pixel(0, 0))

    engine.wait(MOVE_DURATION)
    assert get(board, 0, 0) == "wR"

    engine.wait(MOVE_DURATION)
    assert get(board, 0, 0) == "bN"
    assert spy.calls == [("wR", 0), ("bN", 0)]


def test_cannot_select_a_piece_that_is_mid_move():
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))
    assert controller.selected is None

    controller.click(*cell_to_pixel(0, 0))
    assert controller.selected is None


def test_piece_cannot_be_redirected_while_moving():
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))

    engine.wait(MOVE_DURATION)
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(2, 0))

    engine.wait(MOVE_DURATION * 2)
    assert get(board, 0, 2) == "wR"
    assert is_empty(board, 2, 0)


def test_piece_moves_again_immediately_after_arrival_with_no_cooldown():
    engine, controller, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))
    engine.wait(MOVE_DURATION * 2)
    assert get(board, 0, 2) == "wR"

    controller.click(*cell_to_pixel(0, 2))
    assert controller.selected == (0, 2)
    controller.click(*cell_to_pixel(2, 2))
    engine.wait(MOVE_DURATION * 2)

    assert get(board, 2, 2) == "wR"
    assert is_empty(board, 0, 2)


def test_piece_cannot_move_again_while_resting_after_a_move():
    rows = [["wR", ".", "."], [".", ".", "."], [".", ".", "."]]
    engine, controller, board = make_engine(rows, long_rest_duration=500)

    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))
    engine.wait(MOVE_DURATION * 2)
    assert get(board, 0, 2) == "wR"

    result = engine.request_move(Position(0, 2), Position(2, 2))
    assert result == ActionResult(False, ActionResultReason.RESTING)
    assert get(board, 0, 2) == "wR"

    engine.wait(500)
    result = engine.request_move(Position(0, 2), Position(2, 2))
    assert result.is_accepted


def test_piece_cannot_jump_while_resting_after_a_move():
    rows = [["wR", ".", "."], [".", ".", "."], [".", ".", "."]]
    engine, controller, board = make_engine(rows, long_rest_duration=500)

    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))
    engine.wait(MOVE_DURATION * 2)

    engine.request_jump(Position(0, 2))
    assert not engine.arbiter.is_jumping_on(Position(0, 2))

    engine.wait(500)
    engine.request_jump(Position(0, 2))
    assert engine.arbiter.is_jumping_on(Position(0, 2))


def test_piece_rests_after_a_jump_ends_and_can_act_again_once_it_elapses():
    rows = [["wR", ".", "."], [".", ".", "."], [".", ".", "."]]
    engine, controller, board = make_engine(rows, short_rest_duration=300)

    engine.request_jump(Position(0, 0))
    engine.wait(JUMP_DURATION)

    result = engine.request_move(Position(0, 0), Position(0, 1))
    assert result == ActionResult(False, ActionResultReason.RESTING)

    engine.wait(300)
    result = engine.request_move(Position(0, 0), Position(0, 1))
    assert result.is_accepted


def test_cooldown_only_starts_once_a_piece_truly_lands_not_at_a_mid_flight_capture():
    rows = [
        [".", ".", "bR", ".", "."],
        [".", ".", ".", ".", "."],
        ["wR", ".", ".", ".", "."],
        [".", ".", ".", ".", "."],
        [".", ".", ".", ".", "."],
    ]
    engine, controller, board = make_engine(rows, move_duration=100, long_rest_duration=50)
    black_id = board.piece_at(Position(0, 2)).id

    engine.request_move(Position(2, 0), Position(2, 4))
    engine.wait(50)
    engine.request_move(Position(0, 2), Position(4, 2))

    engine.wait(200)
    assert not engine.arbiter.is_resting(black_id)

    engine.wait(200)
    assert get(board, 4, 2) == "bR"
    assert engine.arbiter.is_resting(black_id)

    engine.wait(50)
    assert not engine.arbiter.is_resting(black_id)


def test_king_captured_on_an_intermediate_cell_ends_the_game_and_skips_later_same_batch_events():
    # A rook flies the length of a column toward the enemy king's cell;
    # the king steps one cell out of the way, into a cell the rook's path
    # already covers, so the rook captures it in passing rather than at
    # its own final destination - proving GameEngine reacts to a capture
    # reported mid-flight (see RealTimeArbiter._resolve_encounter), not
    # only to a capture at a motion's own destination.
    rows = [
        ["wR", "wN", "."],
        [".", ".", "."],
        [".", ".", "."],
        [".", ".", "."],
        ["bK", ".", "."],
    ]
    engine, controller, board = make_engine(rows, move_duration=100, long_rest_duration=1000)
    knight_id = board.piece_at(Position(0, 1)).id
    rook_id = board.piece_at(Position(0, 0)).id

    engine.request_move(Position(0, 0), Position(4, 0))  # rook: reaches (3,0) at t=300
    engine.request_move(Position(4, 0), Position(3, 0))  # king sidesteps into the rook's path, lands t=100

    engine.wait(150)
    # Queued later so its own landing (t=150+200=350) falls chronologically
    # *after* the king capture (t=300), in the very same wait() call below.
    engine.request_move(Position(0, 1), Position(2, 2))

    engine.wait(400)  # covers t=300 (king captured) and t=350 (knight lands)

    assert engine.game_over is True
    # The arbiter mechanically finished resolving everything up to the new
    # clock regardless of game-over - the knight really did land - but
    # GameEngine must never have reached that event to act on it.
    assert get(board, 2, 2) == "wN"
    assert not engine.arbiter.is_resting(knight_id)
    assert not engine.arbiter.is_resting(rook_id)


def test_snapshot_reports_rest_fraction_remaining_for_a_resting_piece():
    rows = [["wR", ".", "."], [".", ".", "."], [".", ".", "."]]
    engine, controller, board = make_engine(rows, long_rest_duration=1000)
    piece_id = board.piece_at(Position(0, 0)).id

    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))
    engine.wait(MOVE_DURATION * 2)

    assert snapshot_piece(engine, piece_id).rest_fraction_remaining == 1.0

    engine.wait(500)
    assert snapshot_piece(engine, piece_id).rest_fraction_remaining == 0.5

    engine.wait(500)
    assert snapshot_piece(engine, piece_id).rest_fraction_remaining is None


def test_snapshot_rest_fraction_remaining_is_none_for_an_idle_piece():
    engine, controller, board = make_engine([["wR", "."]])
    piece_id = board.piece_at(Position(0, 0)).id

    assert snapshot_piece(engine, piece_id).rest_fraction_remaining is None


def test_opposite_color_moves_can_be_in_flight_simultaneously():
    rows = [["bR", ".", "."], [".", ".", "."], [".", ".", "wR"]]
    engine, controller, board = make_engine(rows)
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))

    controller.click(*cell_to_pixel(2, 2))
    controller.click(*cell_to_pixel(2, 0))

    engine.wait(MOVE_DURATION * 2)
    assert get(board, 0, 2) == "bR"
    assert get(board, 2, 0) == "wR"


def test_same_color_moves_can_be_in_flight_simultaneously():
    rows = [["wR", ".", "wN"], [".", ".", "."], [".", ".", "."]]
    engine, controller, board = make_engine(rows)
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(2, 0))

    controller.click(*cell_to_pixel(0, 2))
    controller.click(*cell_to_pixel(2, 1))

    engine.wait(MOVE_DURATION * 2)
    assert get(board, 2, 0) == "wR"
    assert get(board, 2, 1) == "wN"


def test_two_friendly_moves_with_an_exact_arrival_tie_both_stop_short():
    # Equal distance to a shared destination, queued at the same time -
    # a genuine exact tie. Per the documented tie policy (see
    # RealTimeArbiter._resolve_collision / docs), neither friendly
    # reaches the contested cell; both stop one cell short instead.
    rows = [["wR", ".", "."], [".", ".", "."], ["wB", ".", "."]]
    engine, controller, board = make_engine(rows)
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))

    controller.click(*cell_to_pixel(2, 0))
    controller.click(*cell_to_pixel(0, 2))

    engine.wait(MOVE_DURATION * 2)

    assert is_empty(board, 0, 2)
    assert get(board, 0, 1) == "wR"
    assert get(board, 1, 1) == "wB"


def test_two_friendly_motions_racing_non_tied_first_continues_second_stops_short():
    rows = [["wR", "wR", ".", "."]]
    engine, controller, board = make_engine(rows)

    controller.click(*cell_to_pixel(0, 1))
    controller.click(*cell_to_pixel(0, 3))

    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 3))

    engine.wait(MOVE_DURATION * 2)

    assert get(board, 0, 3) == "wR"
    assert get(board, 0, 1) == "wR"
    assert is_empty(board, 0, 2)


def test_same_color_piece_can_enter_a_departed_pieces_source_cell():
    rows = [["wR", ".", "."], [".", ".", "."], [".", "wN", "."]]
    engine, controller, board = make_engine(rows)

    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))
    assert is_empty(board, 0, 0)

    result = engine.request_move(Position(2, 1), Position(0, 0))
    assert result.is_accepted


def test_enemy_piece_can_enter_a_departing_pieces_source_cell():
    rows = [["wR", ".", "."], [".", ".", "."], [".", "bN", "."]]
    engine, controller, board = make_engine(rows)

    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))
    assert is_empty(board, 0, 0)

    result = engine.request_move(Position(2, 1), Position(0, 0))
    assert result.is_accepted


def test_render_returns_current_board_text():
    engine, controller, board = make_engine([["wK", "."], [".", "bK"]])
    engine.wait(0)
    text = BoardPrinter().render(engine.snapshot())
    assert text == "wK .\n. bK"


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
    # wait(0) never advances the clock but still resolves anything
    # already due; a validated move always has duration > 0, so it can
    # never be immediately due the instant it's queued (see docs).
    engine, controller, board = make_engine([["wR", ".", "."]])
    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))

    assert engine.arbiter.advance_time(0) == []

    engine.wait(MOVE_DURATION * 2)
    assert engine.arbiter.advance_time(0) == []


def test_stale_selection_after_capture_is_not_acted_on():
    rows = [["wQ", ".", "."], [".", ".", "."], ["bR", ".", "."]]
    engine, controller, board = make_engine(rows)

    controller.click(*cell_to_pixel(2, 0))
    controller.click(*cell_to_pixel(0, 0))
    assert controller.selected is None

    controller.click(*cell_to_pixel(0, 0))
    assert controller.selected == (0, 0)

    engine.wait(MOVE_DURATION * 2)
    assert get(board, 0, 0) == "bR"

    controller.click(*cell_to_pixel(0, 1))
    assert controller.selected is None


def test_piece_continues_to_destination_after_enemy_moves_into_vacated_source():
    rows = [[".", ".", "."], [".", "bB", "."], ["wR", ".", "."]]
    engine, controller, board = make_engine(rows)

    controller.click(*cell_to_pixel(2, 0))
    controller.click(*cell_to_pixel(0, 0))
    assert is_empty(board, 2, 0)

    controller.click(*cell_to_pixel(1, 1))
    controller.click(*cell_to_pixel(2, 0))

    engine.wait(MOVE_DURATION)
    assert get(board, 2, 0) == "bB"

    controller.click(*cell_to_pixel(2, 0))
    assert controller.selected == (2, 0)

    engine.wait(MOVE_DURATION)
    assert get(board, 0, 0) == "wR"


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
    controller.click(*cell_to_pixel(0, 2))

    snap = snapshot_piece(engine, piece_id)
    assert (snap.row, snap.col) == (0, 0)
    assert (snap.render_row, snap.render_col) == (0.0, 0.0)
    assert snap.is_moving is True


def test_snapshot_render_position_interpolates_midway_through_a_move():
    rows = [["wR", ".", "."]]
    engine, controller, board = make_engine(rows)
    piece_id = board.piece_at(Position(0, 0)).id

    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))

    engine.wait(MOVE_DURATION)

    snap = snapshot_piece(engine, piece_id)
    assert (snap.row, snap.col) == (0, 0)
    assert snap.render_row == 0.0
    assert snap.render_col == 1.0
    assert snap.is_moving is True


def test_snapshot_render_position_matches_destination_after_arrival():
    rows = [["wR", ".", "."]]
    engine, controller, board = make_engine(rows)
    piece_id = board.piece_at(Position(0, 0)).id

    controller.click(*cell_to_pixel(0, 0))
    controller.click(*cell_to_pixel(0, 2))
    engine.wait(MOVE_DURATION * 2)

    snap = snapshot_piece(engine, piece_id)
    assert (snap.row, snap.col) == (0, 2)
    assert (snap.render_row, snap.render_col) == (0.0, 2.0)
    assert snap.is_moving is False
    assert snap.is_jumping is False


def test_snapshot_is_jumping_while_jump_active():
    rows = [["bP", "."]]
    engine, controller, board = make_engine(rows)
    piece_id = board.piece_at(Position(0, 0)).id

    controller.jump(*cell_to_pixel(0, 0))

    snap = snapshot_piece(engine, piece_id)
    assert snap.is_jumping is True
    assert snap.is_moving is False
    assert (snap.render_row, snap.render_col) == (0.0, 0.0)


def test_snapshot_is_idle_by_default():
    rows = [["wK", "."]]
    engine, controller, board = make_engine(rows)
    piece_id = board.piece_at(Position(0, 0)).id

    snap = snapshot_piece(engine, piece_id)
    assert snap.is_moving is False
    assert snap.is_jumping is False
    assert (snap.render_row, snap.render_col) == (0.0, 0.0)
