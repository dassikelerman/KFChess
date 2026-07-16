from model.board import Board
from model.position import Position
from rules.rule_engine import RuleEngine, build_default_registry
from engine.game_conditions import KingCaptureWinCondition, LastRankPromotion
from realtime.real_time_arbiter import RealTimeArbiter
from input.board_mapper import BoardMapper
from input.controller import Controller
from engine.game_engine import GameEngine
from view.click_router import ClickRouter

CELL_SIZE = 100
MOVE_DURATION = 1000
JUMP_DURATION = 1000
LONG_REST_DURATION = 0
SHORT_REST_DURATION = 0


def cell_to_pixel(row, col):
    return col * CELL_SIZE, row * CELL_SIZE


def get(board, row, col):
    piece = board.piece_at(Position(row, col))
    return "." if piece is None else piece.color.value + piece.kind.value


def make_router(rows):
    board = Board(rows)
    registry = build_default_registry(pawn_direction={"w": -1, "b": 1})
    engine = GameEngine(
        board=board,
        rule_engine=RuleEngine(registry),
        arbiter=RealTimeArbiter(board),
        win_condition=KingCaptureWinCondition(),
        promotion_rule=LastRankPromotion(),
        move_duration=MOVE_DURATION,
        jump_duration=JUMP_DURATION,
        long_rest_duration=LONG_REST_DURATION,
        short_rest_duration=SHORT_REST_DURATION,
    )
    board_mapper = BoardMapper(CELL_SIZE, board.width, board.height)
    controller_white = Controller(engine, board_mapper)
    controller_black = Controller(engine, board_mapper)
    router = ClickRouter(engine, board_mapper, controller_white, controller_black)
    return engine, board, controller_white, controller_black, router


def test_first_click_on_a_white_piece_routes_to_the_white_controller():
    engine, board, white, black, router = make_router([["wR", ".", "."], [".", ".", "."], ["bR", ".", "."]])

    router.click(*cell_to_pixel(0, 0))

    assert white.selected == (0, 0)
    assert black.selected is None


def test_first_click_on_a_black_piece_routes_to_the_black_controller():
    engine, board, white, black, router = make_router([["wR", ".", "."], [".", ".", "."], ["bR", ".", "."]])

    router.click(*cell_to_pixel(2, 0))

    assert black.selected == (2, 0)
    assert white.selected is None


def test_second_click_of_a_gesture_stays_with_the_same_controller_even_over_empty_space():
    rows = [["wR", ".", "."], [".", ".", "."], ["bR", ".", "."]]
    engine, board, white, black, router = make_router(rows)

    router.click(*cell_to_pixel(0, 0))
    router.click(*cell_to_pixel(0, 2))

    assert white.selected is None
    assert black.selected is None


def test_a_click_on_the_other_colors_piece_while_active_completes_the_gesture_as_a_capture():
    rows = [["wR", ".", "."], [".", ".", "."], ["bR", ".", "."]]
    engine, board, white, black, router = make_router(rows)

    router.click(*cell_to_pixel(0, 0))
    router.click(*cell_to_pixel(2, 0))

    assert white.selected is None
    engine.wait(MOVE_DURATION * 2)
    assert get(board, 2, 0) == "wR"
    assert black.selected is None


def test_a_click_that_would_be_an_illegal_target_does_not_fall_through_to_the_other_side():
    rows = [["wR", ".", "."], [".", ".", "."], [".", "bR", "."]]
    engine, board, white, black, router = make_router(rows)

    router.click(*cell_to_pixel(0, 0))
    router.click(*cell_to_pixel(2, 1))

    assert white.selected is None
    assert black.selected is None


def test_illegal_target_cancels_the_gesture_and_frees_the_router():
    rows = [["wR", ".", "."], [".", "bR", "."], [".", ".", "."]]
    engine, board, white, black, router = make_router(rows)

    router.click(*cell_to_pixel(0, 0))
    router.click(*cell_to_pixel(1, 1))

    assert white.selected is None

    router.click(*cell_to_pixel(0, 0))
    assert white.selected == (0, 0)


def test_after_an_illegal_target_the_next_click_can_route_to_the_other_side():
    rows = [["wR", ".", "."], [".", ".", "."], [".", "bR", "."]]
    engine, board, white, black, router = make_router(rows)

    router.click(*cell_to_pixel(0, 0))
    router.click(*cell_to_pixel(2, 1))
    assert white.selected is None

    router.click(*cell_to_pixel(2, 1))
    assert black.selected == (2, 1)


def test_click_on_empty_cell_with_nobody_active_is_a_no_op():
    rows = [["wR", ".", "."], [".", ".", "."], ["bR", ".", "."]]
    engine, board, white, black, router = make_router(rows)

    router.click(*cell_to_pixel(1, 1))

    assert white.selected is None
    assert black.selected is None


def test_after_a_completed_gesture_the_next_click_can_route_to_the_other_side():
    rows = [["wR", ".", "."], [".", ".", "."], ["bR", ".", "."]]
    engine, board, white, black, router = make_router(rows)

    router.click(*cell_to_pixel(0, 0))
    router.click(*cell_to_pixel(0, 1))

    router.click(*cell_to_pixel(2, 0))

    assert black.selected == (2, 0)
    assert white.selected is None


# -- jump() routing -----------------------------------------------------


def test_jump_on_a_white_piece_routes_to_the_white_controller():
    rows = [["wR", ".", "."], [".", ".", "."], ["bR", ".", "."]]
    engine, board, white, black, router = make_router(rows)

    router.jump(*cell_to_pixel(0, 0))

    assert engine.arbiter.is_jumping_on(Position(0, 0))


def test_jump_on_a_black_piece_routes_to_the_black_controller():
    rows = [["wR", ".", "."], [".", ".", "."], ["bR", ".", "."]]
    engine, board, white, black, router = make_router(rows)

    router.jump(*cell_to_pixel(2, 0))

    assert engine.arbiter.is_jumping_on(Position(2, 0))


def test_jump_on_empty_cell_is_a_no_op():
    rows = [["wR", ".", "."], [".", ".", "."], ["bR", ".", "."]]
    engine, board, white, black, router = make_router(rows)

    router.jump(*cell_to_pixel(1, 1))

    assert white.selected is None
    assert black.selected is None
    assert engine.arbiter.active_motions() == []


def test_jump_does_not_disturb_an_unrelated_active_gesture_on_the_other_side():
    rows = [["wR", ".", "."], [".", ".", "."], ["bR", ".", "."]]
    engine, board, white, black, router = make_router(rows)

    router.click(*cell_to_pixel(0, 0))
    assert white.selected == (0, 0)

    router.jump(*cell_to_pixel(2, 0))

    assert engine.arbiter.is_jumping_on(Position(2, 0))
    assert white.selected == (0, 0)


def test_jump_on_the_active_side_clears_its_pending_gesture():
    rows = [["wR", "wB", "."], [".", ".", "."], ["bR", ".", "."]]
    engine, board, white, black, router = make_router(rows)

    router.click(*cell_to_pixel(0, 0))
    assert white.selected == (0, 0)

    router.jump(*cell_to_pixel(0, 1))

    assert engine.arbiter.is_jumping_on(Position(0, 1))
    assert white.selected is None

    router.click(*cell_to_pixel(2, 0))
    assert black.selected == (2, 0)
