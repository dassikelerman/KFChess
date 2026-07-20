from app.game_builder import build_game
from events.dispatcher import EventDispatcher
from events.game_events import (
    CaptureEvent,
    GameOverEvent,
    IllegalActionEvent,
    JumpCompletedEvent,
    MotionStoppedEvent,
    MoveCompletedEvent,
    PromotionEvent,
)
from events.serialization import to_dict
from model.piece import PieceColor, PieceKind
from model.position import Position
from server.network_publisher import NetworkPublisher

AT = Position(0, 0)

SAMPLE_EVENTS = [
    MoveCompletedEvent(
        piece_id="p1", piece_kind=PieceKind.ROOK, piece_color=PieceColor.WHITE,
        destination=AT, at_ms=100,
    ),
    CaptureEvent(
        piece_id="p1", piece_kind=PieceKind.ROOK, piece_color=PieceColor.WHITE,
        captured_piece_id="p2", captured_kind=PieceKind.PAWN, captured_color=PieceColor.BLACK,
        at=AT, at_ms=200,
    ),
    JumpCompletedEvent(
        piece_id="p1", piece_kind=PieceKind.KNIGHT, piece_color=PieceColor.BLACK,
        cell=AT, at_ms=300,
    ),
    MotionStoppedEvent(
        piece_id="p1", piece_kind=PieceKind.QUEEN, piece_color=PieceColor.WHITE,
        at=AT, at_ms=400,
    ),
    PromotionEvent(
        piece_id="p1", piece_color=PieceColor.WHITE,
        from_kind=PieceKind.PAWN, to_kind=PieceKind.QUEEN,
        at=AT, at_ms=500,
    ),
    GameOverEvent(winner_color=PieceColor.BLACK, at_ms=600),
    IllegalActionEvent(piece_id="p1", destination=AT, at_ms=700),
]


def make_publisher():
    dispatcher = EventDispatcher()
    broadcast = []
    NetworkPublisher(dispatcher, broadcast.append)
    return dispatcher, broadcast


def test_each_game_event_type_is_broadcast_as_its_to_dict_form():
    dispatcher, broadcast = make_publisher()

    for event in SAMPLE_EVENTS:
        dispatcher.publish(event)

    assert broadcast == [to_dict(event) for event in SAMPLE_EVENTS]


def test_broadcast_fn_receives_nothing_until_an_event_is_published():
    dispatcher, broadcast = make_publisher()
    assert broadcast == []


def test_snapshot_payload_returns_the_engines_snapshot_plus_the_clock():
    game = build_game(["wK .", ". ."])
    dispatcher = EventDispatcher()
    publisher = NetworkPublisher(dispatcher, broadcast_fn=lambda payload: None)

    payload = publisher.snapshot_payload(game)

    expected = to_dict(game.engine.snapshot())
    expected["clock_ms"] = game.engine.clock
    assert payload == expected
    assert payload["type"] == "GameSnapshot"
    assert payload["clock_ms"] == game.engine.clock
