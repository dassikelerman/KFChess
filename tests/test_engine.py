import pytest

from config import settings
from board.text_board import TextBoardRepresentation
from rules.rule_registry import build_default_registry
from rules.game_conditions import KingCaptureWinCondition, LastRankPromotion, WinCondition, PromotionRule
from game.engine import GameEngine
from game.renderer import BoardRenderer


class NeverEndsWinCondition(WinCondition):
    """Fake collaborator used to test engine behaviour in isolation,
    injected instead of monkeypatching KingCaptureWinCondition."""

    def is_game_over(self, captured_piece):
        return False


class NoPromotion(PromotionRule):
    def promote(self, piece, row, board_height):
        return piece


def make_engine(rows, win_condition=None, promotion_rule=None):
    board = TextBoardRepresentation(rows)
    registry = build_default_registry(settings)
    return GameEngine(
        board=board,
        rule_registry=registry,
        win_condition=win_condition or KingCaptureWinCondition(),
        promotion_rule=promotion_rule or LastRankPromotion(),
        config=settings,
    ), board


def cell_to_pixel(row, col):
    return col * settings.CELL_SIZE, row * settings.CELL_SIZE


def test_click_selects_own_piece():
    engine, board = make_engine([["wK", "."], [".", "."]])
    x, y = cell_to_pixel(0, 0)
    engine.handle_click(x, y)
    assert engine.selected == (0, 0)


def test_click_out_of_bounds_is_ignored():
    engine, board = make_engine([["wK", "."], [".", "."]])
    engine.handle_click(-1, -1)
    assert engine.selected is None


def test_click_empty_cell_with_no_selection_is_ignored():
    engine, board = make_engine([["wK", "."], [".", "."]])
    engine.handle_click(*cell_to_pixel(0, 1))
    assert engine.selected is None
    assert board.get(0, 0) == "wK"


def test_pixel_to_cell_matches_spec_examples():
    # click 50 50 -> center of the top-left cell (0, 0)
    # click 150 50 -> the next cell to the right (0, 1)
    engine, board = make_engine([["wR", "wQ", "."], [".", ".", "."], [".", ".", "."]])
    engine.handle_click(50, 50)
    assert engine.selected == (0, 0)
    engine.handle_click(150, 50)
    assert engine.selected == (0, 1)  # friendly piece: selection replaced, not moved
    assert board.get(0, 0) == "wR"
    assert board.get(0, 1) == "wQ"


def test_click_friendly_piece_replaces_selection():
    engine, board = make_engine([["wR", "wQ", "."], [".", ".", "."], [".", ".", "."]])
    engine.handle_click(*cell_to_pixel(0, 0))
    assert engine.selected == (0, 0)

    engine.handle_click(*cell_to_pixel(0, 1))
    assert engine.selected == (0, 1)
    # no move was queued for either piece
    assert board.get(0, 0) == "wR"
    assert board.get(0, 1) == "wQ"


def test_click_on_busy_friendly_piece_does_not_replace_selection():
    engine, board = make_engine([["wR", ".", "."], ["wB", ".", "."], [".", ".", "."]])
    engine.handle_click(*cell_to_pixel(0, 0))
    engine.handle_click(*cell_to_pixel(0, 2))  # rook move queued, (0, 0) now busy
    assert engine.selected is None

    engine.handle_click(*cell_to_pixel(1, 0))  # select the bishop
    assert engine.selected == (1, 0)

    engine.handle_click(*cell_to_pixel(0, 0))  # rook's old cell is still busy
    assert engine.selected == (1, 0)  # selection unchanged


def test_selecting_then_moving_starts_a_move():
    engine, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    engine.handle_click(*cell_to_pixel(0, 0))
    engine.handle_click(*cell_to_pixel(0, 2))

    assert engine.selected is None
    assert board.get(0, 0) == "wR"  # piece stays at the source until the move lands


def test_move_lands_after_move_duration_elapses():
    engine, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    engine.handle_click(*cell_to_pixel(0, 0))
    engine.handle_click(*cell_to_pixel(0, 2))

    engine.wait(settings.MOVE_DURATION * 2)  # 2-square move takes 2x as long
    assert board.get(0, 2) == "wR"
    assert board.is_empty(0, 0)


def test_illegal_move_keeps_selection_and_piece_in_place():
    engine, board = make_engine([["wN", ".", "."], [".", ".", "."], [".", ".", "."]])
    engine.handle_click(*cell_to_pixel(0, 0))
    engine.handle_click(*cell_to_pixel(0, 1))  # not a legal knight move

    assert engine.selected == (0, 0)
    assert board.get(0, 0) == "wN"


def test_king_legal_one_step_move_lands():
    engine, board = make_engine([["wK", ".", "."], [".", ".", "."], [".", ".", "."]])
    engine.handle_click(*cell_to_pixel(0, 0))
    engine.handle_click(*cell_to_pixel(1, 1))
    engine.wait(settings.MOVE_DURATION)

    assert board.get(1, 1) == "wK"
    assert board.is_empty(0, 0)


def test_king_illegal_two_cell_move_is_ignored():
    engine, board = make_engine([["wK", ".", "."], [".", ".", "."], [".", ".", "."]])
    engine.handle_click(*cell_to_pixel(0, 0))
    engine.handle_click(*cell_to_pixel(2, 0))  # two cells: illegal for a king
    engine.wait(settings.MOVE_DURATION * 2)

    assert engine.selected == (0, 0)
    assert board.get(0, 0) == "wK"


def test_rook_illegal_diagonal_move_is_ignored():
    engine, board = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    engine.handle_click(*cell_to_pixel(0, 0))
    engine.handle_click(*cell_to_pixel(2, 2))  # diagonal: illegal for a rook
    engine.wait(settings.MOVE_DURATION * 2)

    assert engine.selected == (0, 0)
    assert board.get(0, 0) == "wR"


def test_bishop_legal_diagonal_move_lands():
    engine, board = make_engine([["wB", ".", "."], [".", ".", "."], [".", ".", "."]])
    engine.handle_click(*cell_to_pixel(0, 0))
    engine.handle_click(*cell_to_pixel(2, 2))
    engine.wait(settings.MOVE_DURATION * 2)

    assert board.get(2, 2) == "wB"
    assert board.is_empty(0, 0)


def test_bishop_illegal_straight_move_is_ignored():
    engine, board = make_engine([["wB", ".", "."], [".", ".", "."], [".", ".", "."]])
    engine.handle_click(*cell_to_pixel(0, 0))
    engine.handle_click(*cell_to_pixel(0, 2))  # straight: illegal for a bishop
    engine.wait(settings.MOVE_DURATION * 2)

    assert engine.selected == (0, 0)
    assert board.get(0, 0) == "wB"


def test_queen_legal_straight_and_diagonal_moves_land():
    engine, board = make_engine([["wQ", ".", "."], [".", ".", "."], [".", ".", "."]])
    engine.handle_click(*cell_to_pixel(0, 0))
    engine.handle_click(*cell_to_pixel(0, 2))
    engine.wait(settings.MOVE_DURATION * 2)
    assert board.get(0, 2) == "wQ"

    engine.handle_click(*cell_to_pixel(0, 2))
    engine.handle_click(*cell_to_pixel(2, 0))
    engine.wait(settings.MOVE_DURATION * 2)
    assert board.get(2, 0) == "wQ"


def test_knight_legal_l_shape_move_lands():
    engine, board = make_engine([["wN", ".", "."], [".", ".", "."], [".", ".", "."]])
    engine.handle_click(*cell_to_pixel(0, 0))
    engine.handle_click(*cell_to_pixel(2, 1))
    engine.wait(settings.MOVE_DURATION * 2)

    assert board.get(2, 1) == "wN"
    assert board.is_empty(0, 0)


def test_rook_blocked_by_piece_is_ignored():
    engine, board = make_engine([["wR", "bP", "."], [".", ".", "."], [".", ".", "."]])
    engine.handle_click(*cell_to_pixel(0, 0))
    engine.handle_click(*cell_to_pixel(0, 2))  # blocked by the piece at (0, 1)
    engine.wait(settings.MOVE_DURATION * 2)

    assert engine.selected == (0, 0)
    assert board.get(0, 0) == "wR"
    assert board.get(0, 1) == "bP"


def test_bishop_blocked_by_piece_is_ignored():
    engine, board = make_engine([["wB", ".", "."], [".", "bP", "."], [".", ".", "."]])
    engine.handle_click(*cell_to_pixel(0, 0))
    engine.handle_click(*cell_to_pixel(2, 2))  # blocked by the piece at (1, 1)
    engine.wait(settings.MOVE_DURATION * 2)

    assert engine.selected == (0, 0)
    assert board.get(0, 0) == "wB"
    assert board.get(1, 1) == "bP"


def test_knight_jumps_over_blockers_and_lands():
    engine, board = make_engine([["wN", "wP", "."], ["wP", ".", "."], [".", ".", "."]])
    engine.handle_click(*cell_to_pixel(0, 0))
    engine.handle_click(*cell_to_pixel(2, 1))
    engine.wait(settings.MOVE_DURATION * 2)

    assert board.get(2, 1) == "wN"
    assert board.is_empty(0, 0)
    # blockers were untouched, proving the knight jumped rather than moved through them
    assert board.get(0, 1) == "wP"
    assert board.get(1, 0) == "wP"


def test_move_captures_enemy_piece_at_destination():
    engine, board = make_engine([["wR", ".", "bP"], [".", ".", "."], [".", ".", "."]])
    engine.handle_click(*cell_to_pixel(0, 0))
    engine.handle_click(*cell_to_pixel(0, 2))
    engine.wait(settings.MOVE_DURATION * 2)

    assert board.get(0, 2) == "wR"
    assert board.is_empty(0, 0)


def test_white_pawn_moves_upward():
    # 4-row board: white's start row is height - 1 = 3
    rows = [[".", ".", "."], [".", ".", "."], [".", ".", "."], ["wP", ".", "."]]
    engine, board = make_engine(rows)
    engine.handle_click(*cell_to_pixel(3, 0))
    engine.handle_click(*cell_to_pixel(2, 0))
    engine.wait(settings.MOVE_DURATION)

    assert board.get(2, 0) == "wP"
    assert board.is_empty(3, 0)


def test_black_pawn_moves_downward():
    rows = [["bP", ".", "."], [".", ".", "."], [".", ".", "."], [".", ".", "."]]
    engine, board = make_engine(rows)
    engine.handle_click(*cell_to_pixel(0, 0))
    engine.handle_click(*cell_to_pixel(1, 0))
    engine.wait(settings.MOVE_DURATION)

    assert board.get(1, 0) == "bP"
    assert board.is_empty(0, 0)


def test_pawn_double_step_off_start_row_is_ignored():
    # pawn sits on row 2, which is not white's start row (3) on this 4-row board
    rows = [[".", ".", "."], [".", ".", "."], ["wP", ".", "."], [".", ".", "."]]
    engine, board = make_engine(rows)
    engine.handle_click(*cell_to_pixel(2, 0))
    engine.handle_click(*cell_to_pixel(0, 0))
    engine.wait(settings.MOVE_DURATION * 2)

    assert engine.selected == (2, 0)
    assert board.get(2, 0) == "wP"


def test_pawn_cannot_capture_forward():
    rows = [[".", ".", "."], ["bP", ".", "."], ["wP", ".", "."], [".", ".", "."]]
    engine, board = make_engine(rows)
    engine.handle_click(*cell_to_pixel(2, 0))
    engine.handle_click(*cell_to_pixel(1, 0))
    engine.wait(settings.MOVE_DURATION)

    assert engine.selected == (2, 0)
    assert board.get(2, 0) == "wP"
    assert board.get(1, 0) == "bP"


def test_pawn_captures_diagonally():
    rows = [[".", ".", "."], [".", "bP", "."], ["wP", ".", "."], [".", ".", "."]]
    engine, board = make_engine(rows)
    engine.handle_click(*cell_to_pixel(2, 0))
    engine.handle_click(*cell_to_pixel(1, 1))
    engine.wait(settings.MOVE_DURATION)

    assert board.get(1, 1) == "wP"
    assert board.is_empty(2, 0)


def test_cannot_capture_own_color_piece_stays_in_place():
    engine, board = make_engine([["wR", ".", "wP"], [".", ".", "."], [".", ".", "."]])
    engine.handle_click(*cell_to_pixel(0, 0))
    engine.handle_click(*cell_to_pixel(0, 2))
    engine.wait(settings.MOVE_DURATION * 2)

    # clicking a friendly piece replaces the selection instead of capturing it
    assert engine.selected == (0, 2)
    assert board.get(0, 0) == "wR"
    assert board.get(0, 2) == "wP"


def test_king_capture_ends_the_game():
    rows = [["wR", ".", "bK"], [".", ".", "."], [".", ".", "."]]
    engine, board = make_engine(rows)
    engine.handle_click(*cell_to_pixel(0, 0))
    engine.handle_click(*cell_to_pixel(0, 2))
    engine.wait(settings.MOVE_DURATION * 2)

    assert engine.game_over is True


def test_injected_win_condition_overrides_default_behaviour():
    rows = [["wR", ".", "bK"], [".", ".", "."], [".", ".", "."]]
    engine, board = make_engine(rows, win_condition=NeverEndsWinCondition())
    engine.handle_click(*cell_to_pixel(0, 0))
    engine.handle_click(*cell_to_pixel(0, 2))
    engine.wait(settings.MOVE_DURATION * 2)

    assert engine.game_over is False


def test_jump_intercepts_a_move_of_the_opposite_color():
    rows = [["wR", "bP"], [".", "."]]
    engine, board = make_engine(rows)
    engine.handle_click(*cell_to_pixel(0, 0))
    engine.handle_click(*cell_to_pixel(0, 1))
    engine.handle_jump(*cell_to_pixel(0, 1))

    engine.wait(settings.JUMP_DURATION)
    assert board.get(0, 1) == "bP"  # move was intercepted, target unchanged


def test_pawn_promotion_on_arrival():
    # white pawn one step from the last rank (row 0)
    rows = [[".", ".", "."], ["wP", ".", "."], [".", ".", "."]]
    engine, board = make_engine(rows)

    engine.handle_click(*cell_to_pixel(1, 0))
    engine.handle_click(*cell_to_pixel(0, 0))
    engine.wait(settings.MOVE_DURATION)

    assert board.get(0, 0) == "wQ"


def test_injected_promotion_rule_overrides_default_behaviour():
    rows = [[".", ".", "."], ["wP", ".", "."], [".", ".", "."]]
    engine, board = make_engine(rows, promotion_rule=NoPromotion())

    engine.handle_click(*cell_to_pixel(1, 0))
    engine.handle_click(*cell_to_pixel(0, 0))
    engine.wait(settings.MOVE_DURATION)

    assert board.get(0, 0) == "wP"


def test_render_returns_current_board_text():
    engine, board = make_engine([["wK", "."], [".", "bK"]])
    text = engine.render(BoardRenderer())
    assert text == "wK .\n. bK"
