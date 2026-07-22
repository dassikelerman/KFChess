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
from protocol.serialization import to_dict
from model.piece import PieceColor, PieceKind
from model.position import Position
from server.network_publisher import NetworkPublisher

AT = Position(0, 0)

BROADCAST_SAMPLE_EVENTS = [
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
]

ILLEGAL_ACTION_SAMPLE = IllegalActionEvent(piece_id="p1", destination=AT, at_ms=700)


def make_publisher():
    dispatcher = EventDispatcher()
    broadcast = []
    unicast_calls = []
    NetworkPublisher(
        dispatcher, broadcast.append,
        lambda connection, payload: unicast_calls.append((connection, payload)),
    )
    return dispatcher, broadcast, unicast_calls


def test_each_domain_game_event_type_is_broadcast_as_its_to_dict_form():
    dispatcher, broadcast, _ = make_publisher()

    for event in BROADCAST_SAMPLE_EVENTS:
        dispatcher.publish(event)

    assert broadcast == [to_dict(event) for event in BROADCAST_SAMPLE_EVENTS]


def test_broadcast_fn_receives_nothing_until_an_event_is_published():
    dispatcher, broadcast, _ = make_publisher()
    assert broadcast == []


def test_illegal_action_event_published_on_the_dispatcher_does_not_broadcast():
    # IllegalActionEvent is unicast-only (server/session.py builds and
    # unicasts it directly) - even if something else were to publish one
    # on the shared dispatcher, NetworkPublisher must not broadcast it.
    dispatcher, broadcast, unicast_calls = make_publisher()

    dispatcher.publish(ILLEGAL_ACTION_SAMPLE)

    assert broadcast == []
    assert unicast_calls == []


def test_unicast_calls_unicast_fn_with_exactly_that_connection_and_the_serialized_event():
    broadcast = []
    unicast_calls = []
    publisher = NetworkPublisher(EventDispatcher(), broadcast.append, lambda c, p: unicast_calls.append((c, p)))

    publisher.unicast("conn-a", ILLEGAL_ACTION_SAMPLE)

    assert unicast_calls == [("conn-a", to_dict(ILLEGAL_ACTION_SAMPLE))]
    assert broadcast == []
