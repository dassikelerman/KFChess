from config import settings
from model.board import TextBoardRepresentation
from rules.rule_engine import KingCaptureWinCondition, LastRankPromotion, WinCondition, PromotionRule
from realtime.realtime_arbiter import RealtimeArbiter


class NeverEndsWinCondition(WinCondition):
    def is_game_over(self, captured_piece):
        return False


class NoPromotion(PromotionRule):
    def promote(self, piece, row, board_height):
        return piece


def make_arbiter(rows, win_condition=None, promotion_rule=None, config=settings):
    board = TextBoardRepresentation(rows)
    arbiter = RealtimeArbiter(
        board,
        win_condition or KingCaptureWinCondition(),
        promotion_rule or LastRankPromotion(),
        config,
    )
    return arbiter, board


def test_initial_state_is_idle():
    arbiter, board = make_arbiter([["wR", ".", "."]])
    assert arbiter.clock == 0
    assert arbiter.game_over is False
    assert arbiter.is_busy((0, 0)) is False
    assert arbiter.opposite_color_moving("w") is False


def test_enqueue_move_marks_source_cell_busy():
    arbiter, board = make_arbiter([["wR", ".", "."]])
    arbiter.enqueue_move("wR", (0, 0), (0, 2), distance=2)
    assert arbiter.is_busy((0, 0)) is True
    assert arbiter.opposite_color_moving("b") is True
    assert arbiter.opposite_color_moving("w") is False


def test_enqueue_jump_marks_cell_busy():
    arbiter, board = make_arbiter([["bP", ".", "."]])
    arbiter.enqueue_jump("bP", (0, 0))
    assert arbiter.is_busy((0, 0)) is True


def test_tick_advances_clock_and_settles_arrived_move():
    arbiter, board = make_arbiter([["wR", ".", "."]])
    arbiter.enqueue_move("wR", (0, 0), (0, 2), distance=2)
    arbiter.tick(settings.MOVE_DURATION * 2)
    assert arbiter.clock == settings.MOVE_DURATION * 2
    assert board.get(0, 2) == "wR"
    assert board.is_empty(0, 0)
    assert arbiter.is_busy((0, 0)) is False


def test_resolve_without_tick_does_not_advance_clock():
    arbiter, board = make_arbiter([["wR", ".", "."]])
    arbiter.enqueue_move("wR", (0, 0), (0, 2), distance=2)
    arbiter.resolve()
    assert arbiter.clock == 0
    assert board.get(0, 0) == "wR"  # not enough time has passed


def test_move_capturing_king_sets_game_over():
    arbiter, board = make_arbiter([["wR", ".", "bK"]])
    arbiter.enqueue_move("wR", (0, 0), (0, 2), distance=2)
    arbiter.tick(settings.MOVE_DURATION * 2)
    assert arbiter.game_over is True


def test_injected_win_condition_overrides_default():
    arbiter, board = make_arbiter([["wR", ".", "bK"]], win_condition=NeverEndsWinCondition())
    arbiter.enqueue_move("wR", (0, 0), (0, 2), distance=2)
    arbiter.tick(settings.MOVE_DURATION * 2)
    assert arbiter.game_over is False


def test_injected_promotion_rule_overrides_default():
    arbiter, board = make_arbiter([[".", ".", "."], ["wP", ".", "."], [".", ".", "."]], promotion_rule=NoPromotion())
    arbiter.enqueue_move("wP", (1, 0), (0, 0), distance=1)
    arbiter.tick(settings.MOVE_DURATION)
    assert board.get(0, 0) == "wP"  # not promoted, thanks to injected rule


def test_jump_intercepts_move_of_opposite_color():
    arbiter, board = make_arbiter([["wR", "bP"], [".", "."]])
    arbiter.enqueue_move("wR", (0, 0), (0, 1), distance=1)
    arbiter.enqueue_jump("bP", (0, 1))
    arbiter.tick(settings.JUMP_DURATION)
    assert board.get(0, 1) == "bP"  # target unchanged, move intercepted
    assert board.is_empty(0, 0)  # arriving piece removed entirely


def test_jump_expires_after_its_duration():
    arbiter, board = make_arbiter([["bP", ".", "."]])
    arbiter.enqueue_jump("bP", (0, 0))
    arbiter.tick(settings.JUMP_DURATION)
    assert arbiter.is_busy((0, 0)) is False


def test_two_moves_racing_to_same_destination_first_queued_wins():
    arbiter, board = make_arbiter([["wR", ".", "."], [".", ".", "."], ["wB", ".", "."]])
    arbiter.enqueue_move("wR", (0, 0), (0, 2), distance=2)
    arbiter.enqueue_move("wB", (2, 0), (0, 2), distance=2)
    arbiter.tick(settings.MOVE_DURATION * 2)
    assert board.get(0, 2) == "wR"
    assert board.get(2, 0) == "wB"
