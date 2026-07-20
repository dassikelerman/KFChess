from model.piece import PieceColor, PieceKind
from model.position import Position

from events.dispatcher import EventDispatcher
from events.game_events import (
    CaptureEvent,
    GameOverEvent,
    IllegalActionEvent,
    MoveCompletedEvent,
    PromotionEvent,
)
from events.sound_system import SoundSystem

AT = Position(0, 0)


def move_completed():
    return MoveCompletedEvent(
        piece_id="p1", piece_kind=PieceKind.ROOK, piece_color=PieceColor.WHITE,
        destination=AT, at_ms=0,
    )


def capture():
    return CaptureEvent(
        piece_id="p1", piece_kind=PieceKind.ROOK, piece_color=PieceColor.WHITE,
        captured_piece_id="p2", captured_kind=PieceKind.PAWN, captured_color=PieceColor.BLACK,
        at=AT, at_ms=0,
    )


def promotion():
    return PromotionEvent(
        piece_id="p1", piece_color=PieceColor.WHITE,
        from_kind=PieceKind.PAWN, to_kind=PieceKind.QUEEN,
        at=AT, at_ms=0,
    )


def game_over():
    return GameOverEvent(winner_color=PieceColor.WHITE, at_ms=0)


def illegal_action():
    return IllegalActionEvent(piece_id="p1", destination=AT, at_ms=0)


def test_starts_with_nothing_pending():
    system = SoundSystem(EventDispatcher())
    assert system.drain_pending() == []


def test_move_completed_queues_move_wav():
    dispatcher = EventDispatcher()
    system = SoundSystem(dispatcher)
    dispatcher.publish(move_completed())
    assert system.drain_pending() == ["move.wav"]


def test_capture_queues_capture_wav():
    dispatcher = EventDispatcher()
    system = SoundSystem(dispatcher)
    dispatcher.publish(capture())
    assert system.drain_pending() == ["capture.wav"]


def test_promotion_queues_promotion_wav():
    dispatcher = EventDispatcher()
    system = SoundSystem(dispatcher)
    dispatcher.publish(promotion())
    assert system.drain_pending() == ["promotion.wav"]


def test_game_over_queues_game_over_wav():
    dispatcher = EventDispatcher()
    system = SoundSystem(dispatcher)
    dispatcher.publish(game_over())
    assert system.drain_pending() == ["game_over.wav"]


def test_illegal_action_queues_illegal_move_wav():
    dispatcher = EventDispatcher()
    system = SoundSystem(dispatcher)
    dispatcher.publish(illegal_action())
    assert system.drain_pending() == ["illegal_move.wav"]


def test_drain_pending_clears_the_queue():
    dispatcher = EventDispatcher()
    system = SoundSystem(dispatcher)
    dispatcher.publish(move_completed())
    system.drain_pending()
    assert system.drain_pending() == []


def test_events_queue_in_publish_order():
    dispatcher = EventDispatcher()
    system = SoundSystem(dispatcher)
    dispatcher.publish(move_completed())
    dispatcher.publish(capture())
    dispatcher.publish(illegal_action())
    assert system.drain_pending() == ["move.wav", "capture.wav", "illegal_move.wav"]
