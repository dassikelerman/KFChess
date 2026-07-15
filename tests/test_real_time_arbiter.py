import pytest

from model.board import Board
from model.position import Position
from realtime.real_time_arbiter import RealTimeArbiter


def test_motions_resolve_by_arrival_time_not_insertion_order():
    # Slow motion queued first, fast motion queued second - the fast one
    # has the earlier arrival_time and must resolve first regardless of
    # insertion order into _active_motions.
    board = Board([["wR", "wN"], [".", "."]])
    arbiter = RealTimeArbiter(board)
    rook = board.piece_at(Position(0, 0))
    knight = board.piece_at(Position(0, 1))

    arbiter.start_motion(rook, Position(0, 0), Position(1, 0), duration_ms=400)
    arbiter.start_motion(knight, Position(0, 1), Position(1, 1), duration_ms=100)

    events = arbiter.advance_time(400)  # both are due by now

    assert [event.piece_id for event in events] == [knight.id, rook.id]


def test_motion_not_yet_due_stays_active():
    board = Board([["wR", "."]])
    arbiter = RealTimeArbiter(board)
    rook = board.piece_at(Position(0, 0))

    arbiter.start_motion(rook, Position(0, 0), Position(0, 1), duration_ms=1000)
    events = arbiter.advance_time(999)  # one ms short of arrival

    assert events == []
    assert arbiter.active_motion_for(rook.id) is not None
    # The piece already left the Board the instant the motion started -
    # it travels as data on the Motion itself, not as a Board occupant -
    # so the source reads as empty well before arrival, not "unchanged".
    assert board.piece_at(Position(0, 0)) is None
    assert board.piece_at(Position(0, 1)) is None  # not landed yet either


def test_advance_time_rejects_negative_duration():
    arbiter = RealTimeArbiter(Board([["."]]))
    with pytest.raises(ValueError):
        arbiter.advance_time(-1)


def test_advance_time_zero_does_not_advance_clock_but_still_resolves_due_motions():
    board = Board([["wR", "."]])
    arbiter = RealTimeArbiter(board)
    rook = board.piece_at(Position(0, 0))

    # A zero-duration motion is already due the instant it's queued -
    # arrival_time == the current clock - mirroring how Controller calls
    # wait(0) to flush whatever is already due before acting on a click.
    arbiter.start_motion(rook, Position(0, 0), Position(0, 1), duration_ms=0)

    events = arbiter.advance_time(0)

    assert arbiter.clock == 0
    assert len(events) == 1
    assert board.piece_at(Position(0, 1)) is not None
    assert board.piece_at(Position(0, 0)) is None


def test_empty_guarded_cell_does_not_intercept_arrivals():
    # An "orphaned" jump - guarding a cell nobody currently occupies - must
    # not intercept everything indiscriminately just because there's no
    # defender color to compare against. GameEngine.request_move() now
    # refuses to move a piece off a cell it's guarding, so this can't
    # happen through the public API anymore, but RealTimeArbiter's own
    # start_jump()/start_motion() don't enforce that themselves, so this
    # is tested directly at this level as defense in depth.
    board = Board([[".", "."], ["wR", "."]])
    arbiter = RealTimeArbiter(board)
    rook = board.piece_at(Position(1, 0))

    arbiter.start_jump(Position(0, 0), end_time=1000)  # nobody is at (0, 0)
    arbiter.start_motion(rook, Position(1, 0), Position(0, 0), duration_ms=500)

    events = arbiter.advance_time(500)

    assert len(events) == 1
    assert events[0].captured_piece_id is None  # not intercepted
    assert board.piece_at(Position(0, 0)).id == rook.id  # landed normally


def test_enemy_moving_into_a_vacated_source_does_not_affect_the_departed_motion():
    # The queen leaves (0, 0) the instant her own motion starts. While
    # she's still in flight toward (0, 1), an *enemy* rook is free to
    # move into the now-empty (0, 0) - that's a normal move into empty
    # space, not a capture (the queen isn't there), and her own motion
    # must land at her original destination completely unaffected.
    board = Board([["wQ", ".", "."], [".", ".", "."], ["bR", ".", "."]])
    arbiter = RealTimeArbiter(board)
    queen = board.piece_at(Position(0, 0))
    rook = board.piece_at(Position(2, 0))

    arbiter.start_motion(queen, Position(0, 0), Position(0, 1), duration_ms=1000)
    assert board.piece_at(Position(0, 0)) is None  # the queen's old cell is free immediately

    arbiter.start_motion(rook, Position(2, 0), Position(0, 0), duration_ms=500)
    events = arbiter.advance_time(500)  # rook lands on the now-empty cell - not a capture

    assert events[0].captured_piece_id is None
    assert board.piece_at(Position(0, 0)).id == rook.id

    events = arbiter.advance_time(500)  # the queen's own motion now completes, untouched

    assert len(events) == 1
    assert events[0].piece_id == queen.id
    assert events[0].captured_piece_id is None
    assert board.piece_at(Position(0, 1)).id == queen.id  # she reached her original destination
    assert board.piece_at(Position(0, 0)).id == rook.id  # the rook is unaffected too


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

    assert arbiter.active_motion_for(knight.id) is None  # knight never moved


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

    assert arbiter.active_jump_for(Position(0, 1)) is None  # nothing guards this cell


def test_active_jump_for_returns_none_once_the_jump_expires():
    arbiter = RealTimeArbiter(Board([["bP", "."]]))

    arbiter.start_jump(Position(0, 0), end_time=500)
    arbiter.advance_time(500)  # clock reaches end_time - jump is filtered out

    assert arbiter.active_jump_for(Position(0, 0)) is None


# -- in-transit collisions ---------------------------------------------------


def test_head_on_collision_different_colors_later_arrival_wins_and_continues():
    # White and black move toward each other along the same row, past
    # rather than onto each other - the meeting cell (0, 3) is neither
    # piece's own final destination, so the winner must be seen to
    # continue past it rather than just landing there.
    board = Board([["wR", ".", ".", ".", ".", ".", "bR"]])
    arbiter = RealTimeArbiter(board)
    white = board.piece_at(Position(0, 0))
    black = board.piece_at(Position(0, 6))

    arbiter.start_motion(white, Position(0, 0), Position(0, 4), duration_ms=400)  # 100ms/cell
    arbiter.start_motion(black, Position(0, 6), Position(0, 1), duration_ms=600)  # 120ms/cell

    # white reaches (0,3) at t=300; black reaches it at t=360 - black is
    # later, so black wins the meeting there and keeps heading to (0,1).
    events = arbiter.advance_time(360)

    assert len(events) == 1
    assert events[0].piece_id == black.id
    assert events[0].captured_piece_id == white.id
    assert events[0].destination == Position(0, 3)
    assert board.piece_at(Position(0, 3)) is None  # black is passing through, not landing there
    assert board.piece_at(Position(0, 4)) is None  # white never made it to its own destination either

    events = arbiter.advance_time(240)  # black continues on to its own destination, (0, 1)

    assert len(events) == 1
    assert events[0].piece_id == black.id
    assert board.piece_at(Position(0, 1)).id == black.id


def test_crossing_paths_different_colors_later_arrival_captures_and_continues():
    # Not head-on: white travels along a row, black along a column, and
    # their paths only share a single intersection cell - not either
    # one's final destination - so the winner must be seen to *continue
    # past* the collision point rather than stopping there.
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

    arbiter.start_motion(white, Position(2, 0), Position(2, 4), duration_ms=400)  # crosses col 2 at t=200
    arbiter.advance_time(50)  # black enters the board's motion a bit later
    arbiter.start_motion(black, Position(0, 2), Position(4, 2), duration_ms=400)  # crosses row 2 at t=250

    events = arbiter.advance_time(200)  # up to t=250: the crossing collision resolves

    assert len(events) == 1
    assert events[0].piece_id == black.id
    assert events[0].captured_piece_id == white.id
    assert events[0].destination == Position(2, 2)
    assert board.piece_at(Position(2, 2)) is None  # black is passing through, not landing there

    events = arbiter.advance_time(200)  # black continues on to its own, further destination

    assert len(events) == 1
    assert events[0].piece_id == black.id
    assert board.piece_at(Position(4, 2)).id == black.id


def test_a_piece_starting_later_can_still_catch_up_and_capture():
    # black is already 200ms into a long move (0,0)->(0,4) when white,
    # starting right next to the same shared cell, is queued far behind
    # in time but far ahead in distance. White reaches their shared cell
    # only 50ms after black passes through it and, arriving later,
    # catches and captures black there - despite black's huge head
    # start. The collision is judged purely by actual arrival time.
    board = Board([["bR", ".", ".", "wR", "."]])
    arbiter = RealTimeArbiter(board)
    black = board.piece_at(Position(0, 0))
    white = board.piece_at(Position(0, 3))

    arbiter.start_motion(black, Position(0, 0), Position(0, 4), duration_ms=400)  # 100ms/cell
    arbiter.advance_time(200)  # black is now well underway; white only starts now
    arbiter.start_motion(white, Position(0, 3), Position(0, 1), duration_ms=100)  # 50ms/cell

    # black reaches the shared cell (0, 2) at t=200 (its 2nd step);
    # white reaches it at t=200+50=250 (its 1st step) - white is later,
    # so white wins that meeting and continues on toward (0, 1).
    events = arbiter.advance_time(200)  # covers both the collision (t=250) and white's own landing (t=300)

    assert len(events) == 2
    collision, landing = events
    assert collision.piece_id == white.id
    assert collision.captured_piece_id == black.id
    assert collision.destination == Position(0, 2)
    assert landing.piece_id == white.id
    assert landing.captured_piece_id is None
    assert board.piece_at(Position(0, 1)).id == white.id  # white reached its own destination


def test_exact_simultaneous_meeting_between_enemies_destroys_both():
    board = Board([["wR", ".", "."], [".", ".", "."], ["bR", ".", "."]])
    arbiter = RealTimeArbiter(board)
    white = board.piece_at(Position(0, 0))
    black = board.piece_at(Position(2, 0))

    # Equal distance (2) to the same meeting cell, started at the same
    # time - a genuine exact tie, not "whoever was queued first".
    arbiter.start_motion(white, Position(0, 0), Position(2, 0), duration_ms=1000)
    arbiter.start_motion(black, Position(2, 0), Position(0, 0), duration_ms=1000)

    events = arbiter.advance_time(1000)

    assert {event.piece_id for event in events} == {white.id, black.id}
    # Each event self-reports its own destruction - the documented,
    # deterministic policy for an exact enemy tie: no well-defined
    # winner, so neither survives.
    assert all(event.captured_piece_id == event.piece_id for event in events)
    assert board.piece_at(Position(1, 0)) is None  # nobody actually lands at the meeting cell


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
    arbiter_a.advance_time(2000)  # one big jump

    board_b, arbiter_b = build()
    for _ in range(20):
        arbiter_b.advance_time(100)  # twenty small steps covering the same total span

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
    arbiter.advance_time(500)  # clock is now 500

    arbiter.set_cooldown("wR@0,0", duration_ms=200)

    assert arbiter.rest_remaining_fraction("wR@0,0") == 1.0
    arbiter.advance_time(200)  # ends at clock 700, exactly 200ms of rest
    assert arbiter.rest_remaining_fraction("wR@0,0") is None
