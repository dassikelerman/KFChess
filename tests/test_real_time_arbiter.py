import pytest

from model.board import Board
from model.position import Position
from realtime.real_time_arbiter import RealTimeArbiter


def test_motions_resolve_by_arrival_time_not_insertion_order():
    board = Board([["wR", "wN"], [".", "."]])
    arbiter = RealTimeArbiter(board)
    rook = board.piece_at(Position(0, 0))
    knight = board.piece_at(Position(0, 1))

    arbiter.start_motion(rook, Position(0, 0), Position(1, 0), duration_ms=400)
    arbiter.start_motion(knight, Position(0, 1), Position(1, 1), duration_ms=100)

    events = arbiter.advance_time(400)

    assert [event.piece_id for event in events] == [knight.id, rook.id]


def test_motion_not_yet_due_stays_active():
    board = Board([["wR", "."]])
    arbiter = RealTimeArbiter(board)
    rook = board.piece_at(Position(0, 0))

    arbiter.start_motion(rook, Position(0, 0), Position(0, 1), duration_ms=1000)
    events = arbiter.advance_time(999)

    assert events == []
    assert arbiter.active_motion_for(rook.id) is not None
    assert board.piece_at(Position(0, 0)) is None
    assert board.piece_at(Position(0, 1)) is None


def test_advance_time_rejects_negative_duration():
    arbiter = RealTimeArbiter(Board([["."]]))
    with pytest.raises(ValueError):
        arbiter.advance_time(-1)


def test_advance_time_zero_does_not_advance_clock_but_still_resolves_due_motions():
    board = Board([["wR", "."]])
    arbiter = RealTimeArbiter(board)
    rook = board.piece_at(Position(0, 0))

    arbiter.start_motion(rook, Position(0, 0), Position(0, 1), duration_ms=0)

    events = arbiter.advance_time(0)

    assert arbiter.clock == 0
    assert len(events) == 1
    assert board.piece_at(Position(0, 1)) is not None
    assert board.piece_at(Position(0, 0)) is None


def test_empty_guarded_cell_does_not_intercept_arrivals():
    board = Board([[".", "."], ["wR", "."]])
    arbiter = RealTimeArbiter(board)
    rook = board.piece_at(Position(1, 0))

    arbiter.start_jump(Position(0, 0), end_time=1000)
    arbiter.start_motion(rook, Position(1, 0), Position(0, 0), duration_ms=500)

    events = arbiter.advance_time(500)

    assert len(events) == 1
    assert events[0].captured_piece_id is None
    assert board.piece_at(Position(0, 0)).id == rook.id


def test_enemy_moving_into_a_vacated_source_does_not_affect_the_departed_motion():
    board = Board([["wQ", ".", "."], [".", ".", "."], ["bR", ".", "."]])
    arbiter = RealTimeArbiter(board)
    queen = board.piece_at(Position(0, 0))
    rook = board.piece_at(Position(2, 0))

    arbiter.start_motion(queen, Position(0, 0), Position(0, 1), duration_ms=1000)
    assert board.piece_at(Position(0, 0)) is None

    arbiter.start_motion(rook, Position(2, 0), Position(0, 0), duration_ms=500)
    events = arbiter.advance_time(500)

    assert events[0].captured_piece_id is None
    assert board.piece_at(Position(0, 0)).id == rook.id

    events = arbiter.advance_time(500)

    assert len(events) == 1
    assert events[0].piece_id == queen.id
    assert events[0].captured_piece_id is None
    assert board.piece_at(Position(0, 1)).id == queen.id
    assert board.piece_at(Position(0, 0)).id == rook.id


def test_active_motion_for_returns_the_motion_for_that_piece():
    board = Board([["wR", "wN"], [".", "."]])
    arbiter = RealTimeArbiter(board)
    rook = board.piece_at(Position(0, 0))
    knight = board.piece_at(Position(0, 1))

    arbiter.start_motion(rook, Position(0, 0), Position(1, 0), duration_ms=1000)

    motion = arbiter.active_motion_for(rook.id)
    assert motion is not None
    assert motion.piece_id == rook.id
    assert motion.source == Position(0, 0)
    assert motion.destination == Position(1, 0)

    assert arbiter.active_motion_for(knight.id) is None


def test_active_motion_for_returns_none_after_the_motion_resolves():
    board = Board([["wR", "."]])
    arbiter = RealTimeArbiter(board)
    rook = board.piece_at(Position(0, 0))

    arbiter.start_motion(rook, Position(0, 0), Position(0, 1), duration_ms=500)
    arbiter.advance_time(500)

    assert arbiter.active_motion_for(rook.id) is None


def test_active_jump_for_returns_the_jump_guarding_that_cell():
    arbiter = RealTimeArbiter(Board([["bP", "."]]))

    arbiter.start_jump(Position(0, 0), end_time=1000)

    jump = arbiter.active_jump_for(Position(0, 0))
    assert jump is not None
    assert jump.cell == Position(0, 0)
    assert jump.end_time == 1000

    assert arbiter.active_jump_for(Position(0, 1)) is None


def test_active_jump_for_returns_none_once_the_jump_expires():
    arbiter = RealTimeArbiter(Board([["bP", "."]]))

    arbiter.start_jump(Position(0, 0), end_time=500)
    arbiter.advance_time(500)

    assert arbiter.active_jump_for(Position(0, 0)) is None


# -- in-transit collisions ---------------------------------------------------


def test_head_on_collision_different_colors_later_arrival_wins_and_continues():
    board = Board([["wR", ".", ".", ".", ".", ".", "bR"]])
    arbiter = RealTimeArbiter(board)
    white = board.piece_at(Position(0, 0))
    black = board.piece_at(Position(0, 6))

    arbiter.start_motion(white, Position(0, 0), Position(0, 4), duration_ms=400)
    arbiter.start_motion(black, Position(0, 6), Position(0, 1), duration_ms=600)

    events = arbiter.advance_time(360)

    assert len(events) == 1
    assert events[0].piece_id == black.id
    assert events[0].captured_piece_id == white.id
    assert events[0].destination == Position(0, 3)
    assert board.piece_at(Position(0, 3)) is None
    assert board.piece_at(Position(0, 4)) is None

    events = arbiter.advance_time(240)

    assert len(events) == 1
    assert events[0].piece_id == black.id
    assert board.piece_at(Position(0, 1)).id == black.id


def test_crossing_paths_different_colors_later_arrival_captures_and_continues():
    board = Board([
        [".", ".", "bR", ".", "."],
        [".", ".", ".", ".", "."],
        ["wR", ".", ".", ".", "."],
        [".", ".", ".", ".", "."],
        [".", ".", ".", ".", "."],
    ])
    arbiter = RealTimeArbiter(board)
    white = board.piece_at(Position(2, 0))
    black = board.piece_at(Position(0, 2))

    arbiter.start_motion(white, Position(2, 0), Position(2, 4), duration_ms=400)
    arbiter.advance_time(50)
    arbiter.start_motion(black, Position(0, 2), Position(4, 2), duration_ms=400)

    events = arbiter.advance_time(200)

    assert len(events) == 1
    assert events[0].piece_id == black.id
    assert events[0].captured_piece_id == white.id
    assert events[0].destination == Position(2, 2)
    assert board.piece_at(Position(2, 2)) is None

    events = arbiter.advance_time(200)

    assert len(events) == 1
    assert events[0].piece_id == black.id
    assert board.piece_at(Position(4, 2)).id == black.id


def test_a_piece_starting_later_can_still_catch_up_and_capture():
    board = Board([["bR", ".", ".", "wR", "."]])
    arbiter = RealTimeArbiter(board)
    black = board.piece_at(Position(0, 0))
    white = board.piece_at(Position(0, 3))

    arbiter.start_motion(black, Position(0, 0), Position(0, 4), duration_ms=400)
    arbiter.advance_time(200)
    arbiter.start_motion(white, Position(0, 3), Position(0, 1), duration_ms=100)

    events = arbiter.advance_time(200)

    assert len(events) == 2
    collision, landing = events
    assert collision.piece_id == white.id
    assert collision.captured_piece_id == black.id
    assert collision.destination == Position(0, 2)
    assert landing.piece_id == white.id
    assert landing.captured_piece_id is None
    assert board.piece_at(Position(0, 1)).id == white.id


def test_exact_simultaneous_meeting_between_enemies_destroys_both():
    board = Board([["wR", ".", "."], [".", ".", "."], ["bR", ".", "."]])
    arbiter = RealTimeArbiter(board)
    white = board.piece_at(Position(0, 0))
    black = board.piece_at(Position(2, 0))

    arbiter.start_motion(white, Position(0, 0), Position(2, 0), duration_ms=1000)
    arbiter.start_motion(black, Position(2, 0), Position(0, 0), duration_ms=1000)

    events = arbiter.advance_time(1000)

    assert {event.piece_id for event in events} == {white.id, black.id}
    assert all(event.captured_piece_id == event.piece_id for event in events)
    assert board.piece_at(Position(1, 0)) is None


def test_same_result_for_one_big_wait_as_for_several_small_waits():
    def build():
        board = Board([["wR", ".", "."], [".", ".", "."], ["bR", ".", "."]])
        arbiter = RealTimeArbiter(board)
        white = board.piece_at(Position(0, 0))
        black = board.piece_at(Position(2, 0))
        arbiter.start_motion(white, Position(0, 0), Position(0, 2), duration_ms=1000)
        arbiter.start_motion(black, Position(2, 0), Position(0, 2), duration_ms=1500)
        return board, arbiter

    board_a, arbiter_a = build()
    arbiter_a.advance_time(2000)

    board_b, arbiter_b = build()
    for _ in range(20):
        arbiter_b.advance_time(100)

    assert board_a.snapshot() == board_b.snapshot()


# -- cooldown -----------------------------------------------------------


def test_rest_remaining_fraction_is_none_when_never_rested():
    arbiter = RealTimeArbiter(Board([["wR", "."]]))
    assert arbiter.rest_remaining_fraction("wR@0,0") is None
    assert not arbiter.is_resting("wR@0,0")


def test_rest_remaining_fraction_starts_at_one_and_decreases():
    arbiter = RealTimeArbiter(Board([["wR", "."]]))
    arbiter.set_cooldown("wR@0,0", duration_ms=1000)

    assert arbiter.rest_remaining_fraction("wR@0,0") == 1.0
    assert arbiter.is_resting("wR@0,0")

    arbiter.advance_time(250)
    assert arbiter.rest_remaining_fraction("wR@0,0") == 0.75

    arbiter.advance_time(500)
    assert arbiter.rest_remaining_fraction("wR@0,0") == 0.25


def test_rest_remaining_fraction_is_none_once_the_cooldown_ends():
    arbiter = RealTimeArbiter(Board([["wR", "."]]))
    arbiter.set_cooldown("wR@0,0", duration_ms=1000)

    arbiter.advance_time(1000)

    assert arbiter.rest_remaining_fraction("wR@0,0") is None
    assert not arbiter.is_resting("wR@0,0")


def test_set_cooldown_uses_the_current_clock_as_the_rest_start():
    arbiter = RealTimeArbiter(Board([["wR", "."]]))
    arbiter.advance_time(500)

    arbiter.set_cooldown("wR@0,0", duration_ms=200)

    assert arbiter.rest_remaining_fraction("wR@0,0") == 1.0
    arbiter.advance_time(200)
    assert arbiter.rest_remaining_fraction("wR@0,0") is None
