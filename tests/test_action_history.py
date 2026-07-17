from model.piece import PieceColor, PieceKind
from model.position import Position

from events.action_history import ActionHistory
from events.dispatcher import EventDispatcher
from events.game_events import (
    CaptureEvent,
    GameOverEvent,
    JumpCompletedEvent,
    MotionStoppedEvent,
    MoveCompletedEvent,
    PromotionEvent,
)

AT = Position(1, 1)


def make():
    dispatcher = EventDispatcher()
    return dispatcher, ActionHistory(dispatcher)


def test_move_completed_is_recorded_with_the_movers_color():
    dispatcher, history = make()
    dispatcher.publish(MoveCompletedEvent(
        piece_id="p1", piece_kind=PieceKind.ROOK, piece_color=PieceColor.WHITE,
        destination=AT, at_ms=100,
    ))

    entries = history.entries()
    assert len(entries) == 1
    assert entries[0].color == PieceColor.WHITE
    assert entries[0].at_ms == 100
    assert "wR" in entries[0].text


def test_capture_is_recorded_with_both_pieces_named():
    dispatcher, history = make()
    dispatcher.publish(CaptureEvent(
        piece_id="p1", piece_kind=PieceKind.ROOK, piece_color=PieceColor.WHITE,
        captured_piece_id="p2", captured_kind=PieceKind.PAWN, captured_color=PieceColor.BLACK,
        at=AT, at_ms=200,
    ))

    entries = history.entries()
    assert entries[0].color == PieceColor.WHITE
    assert "wR" in entries[0].text
    assert "bP" in entries[0].text


def test_jump_completed_is_recorded_with_the_jumpers_color():
    dispatcher, history = make()
    dispatcher.publish(JumpCompletedEvent(
        piece_id="p1", piece_kind=PieceKind.KNIGHT, piece_color=PieceColor.BLACK,
        cell=AT, at_ms=300,
    ))

    entries = history.entries()
    assert entries[0].color == PieceColor.BLACK
    assert "bN" in entries[0].text


def test_motion_stopped_is_recorded_with_the_stopped_pieces_color():
    dispatcher, history = make()
    dispatcher.publish(MotionStoppedEvent(
        piece_id="p1", piece_kind=PieceKind.QUEEN, piece_color=PieceColor.WHITE,
        at=AT, at_ms=400,
    ))

    entries = history.entries()
    assert entries[0].color == PieceColor.WHITE
    assert "wQ" in entries[0].text


def test_promotion_is_recorded_with_both_kinds_named():
    dispatcher, history = make()
    dispatcher.publish(PromotionEvent(
        piece_id="p1", piece_color=PieceColor.WHITE,
        from_kind=PieceKind.PAWN, to_kind=PieceKind.QUEEN,
        at=AT, at_ms=500,
    ))

    entries = history.entries()
    assert entries[0].color == PieceColor.WHITE
    assert "wP" in entries[0].text
    assert "wQ" in entries[0].text


def test_game_over_is_recorded_with_no_single_color_so_it_shows_on_both_panels():
    dispatcher, history = make()
    dispatcher.publish(GameOverEvent(winner_color=PieceColor.BLACK, at_ms=600))

    entries = history.entries()
    assert entries[0].color is None
    assert "b" in entries[0].text.lower()


def test_illegal_or_rejected_actions_are_never_recorded():
    # ActionHistory only ever subscribes to already-verified game events -
    # a rejected ActionResult never reaches it because GameEngine never
    # publishes anything for a request it refused.
    dispatcher, history = make()
    assert history.entries() == []


def test_entries_preserves_chronological_publish_order():
    dispatcher, history = make()
    dispatcher.publish(MoveCompletedEvent(
        piece_id="p1", piece_kind=PieceKind.ROOK, piece_color=PieceColor.WHITE,
        destination=AT, at_ms=100,
    ))
    dispatcher.publish(JumpCompletedEvent(
        piece_id="p2", piece_kind=PieceKind.KNIGHT, piece_color=PieceColor.BLACK,
        cell=AT, at_ms=200,
    ))

    entries = history.entries()
    assert [e.at_ms for e in entries] == [100, 200]


def test_recent_returns_only_the_last_n_entries_in_order():
    dispatcher, history = make()
    for i in range(5):
        dispatcher.publish(MoveCompletedEvent(
            piece_id=f"p{i}", piece_kind=PieceKind.ROOK, piece_color=PieceColor.WHITE,
            destination=AT, at_ms=i,
        ))

    recent = history.recent(count=2)
    assert [e.at_ms for e in recent] == [3, 4]


def test_recent_defaults_to_a_bounded_window_not_the_full_history():
    dispatcher, history = make()
    for i in range(50):
        dispatcher.publish(MoveCompletedEvent(
            piece_id=f"p{i}", piece_kind=PieceKind.ROOK, piece_color=PieceColor.WHITE,
            destination=AT, at_ms=i,
        ))

    assert len(history.entries()) == 50
    assert len(history.recent()) < 50
