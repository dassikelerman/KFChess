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
    assert arbiter.has_active_motion(Position(0, 0))
    assert board.piece_at(Position(0, 0)) is rook  # board unchanged until arrival


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


def test_stale_motion_does_not_move_a_different_piece_that_replaced_it_at_source():
    board = Board([["wQ", ".", "."], [".", ".", "."], ["bR", ".", "."]])
    arbiter = RealTimeArbiter(board)
    queen = board.piece_at(Position(0, 0))
    rook = board.piece_at(Position(2, 0))

    # The queen intends to move to (0, 1), queued with a long duration.
    arbiter.start_motion(queen, Position(0, 0), Position(0, 1), duration_ms=1000)
    # Meanwhile the rook lands on the queen's cell first, capturing it.
    arbiter.start_motion(rook, Position(2, 0), Position(0, 0), duration_ms=500)

    arbiter.advance_time(500)
    assert board.piece_at(Position(0, 0)).id == rook.id

    # The queen's motion is now due, but (0, 0) no longer holds the queen.
    events = arbiter.advance_time(500)

    assert events == []  # fizzles: piece_id mismatch, nothing to report
    assert board.piece_at(Position(0, 1)) is None  # queen's destination stays empty
    assert board.piece_at(Position(0, 0)).id == rook.id  # rook untouched
