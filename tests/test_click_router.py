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
    router = ClickRouter(board, board_mapper, controller_white, controller_black)
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

    router.click(*cell_to_pixel(0, 0))  # white selects its rook
    router.click(*cell_to_pixel(0, 2))  # completing move over empty space

    assert white.selected is None  # move queued, selection cleared
    assert black.selected is None  # black was never touched


def test_a_click_on_the_other_colors_piece_while_active_completes_the_gesture_as_a_capture():
    # With one mouse, a click on an enemy piece while a gesture is already
    # active is indistinguishable from "capture that piece" - there's no
    # separate signal meaning "actually, start an independent gesture for
    # the other side instead". The router resolves this by keeping the
    # whole two-click gesture exclusive system-wide: once a side is
    # mid-gesture, every following click - including one landing on an
    # enemy piece - completes *that* gesture, exactly like a normal
    # capture click would with a single controller.
    rows = [["wR", ".", "."], [".", ".", "."], ["bR", ".", "."]]
    engine, board, white, black, router = make_router(rows)

    router.click(*cell_to_pixel(0, 0))  # white selects its rook
    router.click(*cell_to_pixel(2, 0))  # click lands on the black rook

    assert white.selected is None  # white's move (a capture) was queued
    engine.wait(MOVE_DURATION * 2)
    assert get(board, 2, 0) == "wR"  # captured
    assert black.selected is None  # black's controller was never invoked


def test_a_click_that_would_be_an_illegal_target_does_not_fall_through_to_the_other_side():
    # Direct proof of the mutual-exclusion invariant: clicking a black
    # piece that white's selection can't legally reach is read as an
    # (illegal) target for white's pending gesture - it never falls
    # through to start a fresh gesture for black instead.
    rows = [["wR", ".", "."], [".", ".", "."], [".", "bR", "."]]
    engine, board, white, black, router = make_router(rows)

    router.click(*cell_to_pixel(0, 0))  # white selects its rook
    router.click(*cell_to_pixel(2, 1))  # bR - not reachable by a rook move: illegal target

    assert white.selected is None  # cancelled, same as any illegal target
    assert black.selected is None  # black's controller was never invoked


def test_illegal_target_cancels_the_gesture_and_frees_the_router():
    rows = [["wR", ".", "."], [".", "bR", "."], [".", ".", "."]]
    engine, board, white, black, router = make_router(rows)

    router.click(*cell_to_pixel(0, 0))  # white selects its rook
    router.click(*cell_to_pixel(1, 1))  # diagonal - illegal for a rook, selection cancelled

    assert white.selected is None  # cancelled, not kept open

    router.click(*cell_to_pixel(0, 0))  # must select again from scratch
    assert white.selected == (0, 0)


def test_after_an_illegal_target_the_next_click_can_route_to_the_other_side():
    rows = [["wR", ".", "."], [".", ".", "."], [".", "bR", "."]]
    engine, board, white, black, router = make_router(rows)

    router.click(*cell_to_pixel(0, 0))  # white selects its rook
    router.click(*cell_to_pixel(2, 1))  # bR - not reachable by a rook move: illegal, cancelled
    assert white.selected is None

    router.click(*cell_to_pixel(2, 1))  # now read as a fresh click - selects black's rook
    assert black.selected == (2, 1)


def test_click_on_empty_cell_with_nobody_active_is_a_no_op():
    rows = [["wR", ".", "."], [".", ".", "."], ["bR", ".", "."]]
    engine, board, white, black, router = make_router(rows)

    router.click(*cell_to_pixel(1, 1))  # empty cell, nothing selected anywhere

    assert white.selected is None
    assert black.selected is None


def test_after_a_completed_gesture_the_next_click_can_route_to_the_other_side():
    rows = [["wR", ".", "."], [".", ".", "."], ["bR", ".", "."]]
    engine, board, white, black, router = make_router(rows)

    router.click(*cell_to_pixel(0, 0))  # white selects
    router.click(*cell_to_pixel(0, 1))  # white's move completes

    router.click(*cell_to_pixel(2, 0))  # fresh gesture: black's rook

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

    router.jump(*cell_to_pixel(1, 1))  # nothing there

    assert white.selected is None
    assert black.selected is None
    assert not engine.arbiter.has_active_motion()


def test_jump_does_not_disturb_an_unrelated_active_gesture_on_the_other_side():
    rows = [["wR", ".", "."], [".", ".", "."], ["bR", ".", "."]]
    engine, board, white, black, router = make_router(rows)

    router.click(*cell_to_pixel(0, 0))  # white mid-gesture
    assert white.selected == (0, 0)

    router.jump(*cell_to_pixel(2, 0))  # right-click jump on black's rook

    assert engine.arbiter.is_jumping_on(Position(2, 0))
    assert white.selected == (0, 0)  # white's pending gesture is untouched


def test_jump_on_the_active_side_clears_its_pending_gesture():
    rows = [["wR", "wB", "."], [".", ".", "."], ["bR", ".", "."]]
    engine, board, white, black, router = make_router(rows)

    router.click(*cell_to_pixel(0, 0))  # white selects its rook
    assert white.selected == (0, 0)

    router.jump(*cell_to_pixel(0, 1))  # white right-clicks jump on a different white piece

    assert engine.arbiter.is_jumping_on(Position(0, 1))
    assert white.selected is None  # Controller.jump() clears its own selection

    router.click(*cell_to_pixel(2, 0))  # router is free again - routes fresh to black
    assert black.selected == (2, 0)
