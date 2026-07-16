from model.piece import PieceColor, PieceKind
from model.position import Position

from events.dispatcher import EventDispatcher
from events.game_events import CaptureEvent
from events.score_tracker import ScoreTracker

AT = Position(0, 0)


def capture(piece_color, captured_kind):
    return CaptureEvent(
        piece_id="p1", piece_kind=PieceKind.QUEEN, piece_color=piece_color,
        captured_piece_id="p2", captured_kind=captured_kind, captured_color=PieceColor.BLACK,
        at=AT, at_ms=0,
    )


def test_score_starts_at_zero_for_both_colors():
    tracker = ScoreTracker(EventDispatcher())
    assert tracker.snapshot() == {PieceColor.WHITE: 0, PieceColor.BLACK: 0}


def test_capturing_a_pawn_awards_one_point():
    dispatcher = EventDispatcher()
    tracker = ScoreTracker(dispatcher)
    dispatcher.publish(capture(PieceColor.WHITE, PieceKind.PAWN))
    assert tracker.snapshot()[PieceColor.WHITE] == 1


def test_capturing_a_knight_or_bishop_awards_three_points():
    dispatcher = EventDispatcher()
    tracker = ScoreTracker(dispatcher)
    dispatcher.publish(capture(PieceColor.WHITE, PieceKind.KNIGHT))
    dispatcher.publish(capture(PieceColor.WHITE, PieceKind.BISHOP))
    assert tracker.snapshot()[PieceColor.WHITE] == 6


def test_capturing_a_rook_awards_five_points():
    dispatcher = EventDispatcher()
    tracker = ScoreTracker(dispatcher)
    dispatcher.publish(capture(PieceColor.BLACK, PieceKind.ROOK))
    assert tracker.snapshot()[PieceColor.BLACK] == 5


def test_capturing_a_queen_awards_nine_points():
    dispatcher = EventDispatcher()
    tracker = ScoreTracker(dispatcher)
    dispatcher.publish(capture(PieceColor.BLACK, PieceKind.QUEEN))
    assert tracker.snapshot()[PieceColor.BLACK] == 9


def test_capturing_a_king_awards_zero_points():
    dispatcher = EventDispatcher()
    tracker = ScoreTracker(dispatcher)
    dispatcher.publish(capture(PieceColor.WHITE, PieceKind.KING))
    assert tracker.snapshot()[PieceColor.WHITE] == 0


def test_score_is_credited_to_the_capturing_piece_color_not_the_victims():
    dispatcher = EventDispatcher()
    tracker = ScoreTracker(dispatcher)
    dispatcher.publish(capture(PieceColor.WHITE, PieceKind.PAWN))
    snapshot = tracker.snapshot()
    assert snapshot[PieceColor.WHITE] == 1
    assert snapshot[PieceColor.BLACK] == 0


def test_score_accumulates_across_multiple_captures():
    dispatcher = EventDispatcher()
    tracker = ScoreTracker(dispatcher)
    dispatcher.publish(capture(PieceColor.WHITE, PieceKind.PAWN))
    dispatcher.publish(capture(PieceColor.WHITE, PieceKind.ROOK))
    assert tracker.snapshot()[PieceColor.WHITE] == 6


def test_snapshot_returns_an_independent_copy():
    dispatcher = EventDispatcher()
    tracker = ScoreTracker(dispatcher)
    snapshot = tracker.snapshot()
    snapshot[PieceColor.WHITE] = 999
    assert tracker.snapshot()[PieceColor.WHITE] == 0
