import pytest

from model.board import Board
from model.game_state import ArrivalEvent, JumpEndedEvent
from model.piece import PieceColor, PieceKind
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
    assert any(m.piece_id == rook.id for m in arbiter.active_motions())
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


def test_active_motions_reports_the_motion_for_that_piece_with_its_source_and_destination():
    board = Board([["wR", "wN"], [".", "."]])
    arbiter = RealTimeArbiter(board)
    rook = board.piece_at(Position(0, 0))
    knight = board.piece_at(Position(0, 1))

    arbiter.start_motion(rook, Position(0, 0), Position(1, 0), duration_ms=1000)

    motions = {m.piece_id: m for m in arbiter.active_motions()}
    assert rook.id in motions
    assert motions[rook.id].source == Position(0, 0)
    assert motions[rook.id].destination == Position(1, 0)

    assert knight.id not in motions  # knight never moved


def test_active_motions_no_longer_reports_a_motion_once_it_resolves():
    board = Board([["wR", "."]])
    arbiter = RealTimeArbiter(board)
    rook = board.piece_at(Position(0, 0))

    arbiter.start_motion(rook, Position(0, 0), Position(0, 1), duration_ms=500)
    arbiter.advance_time(500)

    assert not any(m.piece_id == rook.id for m in arbiter.active_motions())


def test_is_jumping_on_reflects_which_cell_a_jump_guards():
    arbiter = RealTimeArbiter(Board([["bP", "."]]))

    arbiter.start_jump(Position(0, 0), end_time=1000)

    assert arbiter.is_jumping_on(Position(0, 0))
    assert not arbiter.is_jumping_on(Position(0, 1))


def test_is_jumping_on_becomes_false_once_the_jump_expires():
    arbiter = RealTimeArbiter(Board([["bP", "."]]))

    arbiter.start_jump(Position(0, 0), end_time=500)
    arbiter.advance_time(500)

    assert not arbiter.is_jumping_on(Position(0, 0))


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

    def positions(board):
        return {(piece.color, piece.kind, piece.cell) for piece in board.pieces()}

    assert positions(board_a) == positions(board_b)


# -- motion vs. a piece that landed mid-path ---------------------------------


def test_motion_captures_an_enemy_piece_that_landed_on_an_intermediate_cell_and_continues():
    # A rook flies the length of a column toward a pawn's cell; while it's
    # still in flight, the pawn steps one cell toward the rook - into a
    # cell the rook's own path already covers. Nothing but the arbiter's
    # own event loop tracks this: the pawn's short motion resolves (lands
    # on the Board) well before the rook's clock reaches that cell.
    board = Board([
        ["wR", "."],
        [".", "."],
        [".", "."],
        [".", "."],
        ["bP", "."],
    ])
    arbiter = RealTimeArbiter(board)
    rook = board.piece_at(Position(0, 0))
    pawn = board.piece_at(Position(4, 0))

    arbiter.start_motion(rook, Position(0, 0), Position(4, 0), duration_ms=400)  # 100ms/cell
    arbiter.advance_time(50)
    arbiter.start_motion(pawn, Position(4, 0), Position(3, 0), duration_ms=50)
    arbiter.advance_time(50)  # pawn lands on (3, 0) at t=100, into the rook's path

    events = arbiter.advance_time(300)  # the rook's clock reaches (3, 0) at t=300

    assert events == [
        ArrivalEvent(
            piece_id=rook.id, source=Position(0, 0), destination=Position(3, 0),
            captured_piece_id=pawn.id, king_captured=False,
            piece_kind=PieceKind.ROOK, piece_color=PieceColor.WHITE,
            captured_kind=PieceKind.PAWN, captured_color=PieceColor.BLACK,
        ),
        ArrivalEvent(
            piece_id=rook.id, source=Position(0, 0), destination=Position(4, 0),
            captured_piece_id=None, king_captured=False,
            piece_kind=PieceKind.ROOK, piece_color=PieceColor.WHITE,
        ),
    ]
    assert board.piece_at(Position(3, 0)) is None  # the pawn was captured in passing
    assert board.piece_at(Position(4, 0)).id == rook.id  # the rook reached its own destination


def test_motion_stops_short_of_a_friendly_piece_that_landed_on_an_intermediate_cell():
    board = Board([
        ["wR", "."],
        [".", "."],
        [".", "."],
        [".", "."],
        ["wN", "."],
    ])
    arbiter = RealTimeArbiter(board)
    rook = board.piece_at(Position(0, 0))
    knight = board.piece_at(Position(4, 0))

    arbiter.start_motion(rook, Position(0, 0), Position(4, 0), duration_ms=400)
    arbiter.advance_time(50)
    arbiter.start_motion(knight, Position(4, 0), Position(3, 0), duration_ms=50)
    arbiter.advance_time(50)  # knight lands on (3, 0) at t=100, into the rook's path

    events = arbiter.advance_time(300)

    # Truncated one cell short of (3, 0) - i.e. redirected to (2, 0) - and
    # that shortened motion is now itself due, so it lands normally there.
    assert events == [ArrivalEvent(
        piece_id=rook.id, source=Position(0, 0), destination=Position(2, 0),
        captured_piece_id=None, king_captured=False,
        piece_kind=PieceKind.ROOK, piece_color=PieceColor.WHITE,
    )]
    assert board.piece_at(Position(2, 0)).id == rook.id
    assert board.piece_at(Position(3, 0)).id == knight.id
    assert board.piece_at(Position(4, 0)) is None


def test_motion_captures_a_king_on_an_intermediate_cell_and_reports_it():
    board = Board([
        ["wR", "."],
        [".", "."],
        [".", "."],
        [".", "."],
        ["bK", "."],
    ])
    arbiter = RealTimeArbiter(board)
    rook = board.piece_at(Position(0, 0))
    king = board.piece_at(Position(4, 0))

    arbiter.start_motion(rook, Position(0, 0), Position(4, 0), duration_ms=400)
    arbiter.advance_time(50)
    arbiter.start_motion(king, Position(4, 0), Position(3, 0), duration_ms=50)
    arbiter.advance_time(50)

    events = arbiter.advance_time(300)

    assert events[0] == ArrivalEvent(
        piece_id=rook.id, source=Position(0, 0), destination=Position(3, 0),
        captured_piece_id=king.id, king_captured=True,
        piece_kind=PieceKind.ROOK, piece_color=PieceColor.WHITE,
        captured_kind=PieceKind.KING, captured_color=PieceColor.BLACK,
    )


def test_knight_ignores_a_piece_that_landed_along_its_geometric_path():
    # A knight's path_cells() is only ever its destination - it has no
    # in-transit cells at all, so nothing can be encountered mid-flight.
    board = Board([
        ["wN", ".", "."],
        [".", ".", "."],
        [".", ".", "."],
    ])
    arbiter = RealTimeArbiter(board)
    knight = board.piece_at(Position(0, 0))

    arbiter.start_motion(knight, Position(0, 0), Position(2, 1), duration_ms=200)
    events = arbiter.advance_time(200)

    assert events == [ArrivalEvent(
        piece_id=knight.id, source=Position(0, 0), destination=Position(2, 1),
        captured_piece_id=None, king_captured=False,
        piece_kind=PieceKind.KNIGHT, piece_color=PieceColor.WHITE,
    )]


# -- jump ending ---------------------------------------------------------


def test_advance_time_reports_a_jump_ended_event_when_its_window_elapses():
    board = Board([["bP", "."]])
    arbiter = RealTimeArbiter(board)
    pawn = board.piece_at(Position(0, 0))

    arbiter.start_jump(Position(0, 0), end_time=500)
    events = arbiter.advance_time(500)

    assert events == [JumpEndedEvent(
        piece_id=pawn.id, cell=Position(0, 0),
        piece_kind=PieceKind.PAWN, piece_color=PieceColor.BLACK,
    )]
    assert not arbiter.is_jumping_on(Position(0, 0))


def test_advance_time_does_not_report_a_jump_not_yet_due():
    board = Board([["bP", "."]])
    arbiter = RealTimeArbiter(board)

    arbiter.start_jump(Position(0, 0), end_time=500)
    events = arbiter.advance_time(499)

    assert events == []
    assert arbiter.is_jumping_on(Position(0, 0))


def test_advance_time_reports_no_jump_ended_event_for_an_empty_guarded_cell():
    board = Board([[".", "."]])
    arbiter = RealTimeArbiter(board)

    arbiter.start_jump(Position(0, 0), end_time=500)
    events = arbiter.advance_time(500)

    assert events == []
    assert not arbiter.is_jumping_on(Position(0, 0))


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
