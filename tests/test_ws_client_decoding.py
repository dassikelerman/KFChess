import json

from client.ws_client import WsClient
from engine.snapshot import GameSnapshot, PieceSnapshot
from events.game_events import CaptureEvent, MoveCompletedEvent
from events.serialization import to_dict
from model.piece import PieceColor, PieceKind
from model.position import Position

AT = Position(1, 2)


def make_client():
    return WsClient("ws://unused")


def make_snapshot():
    return GameSnapshot(
        board_width=2, board_height=2,
        pieces=[
            PieceSnapshot(
                id="p1", kind=PieceKind.KING, color=PieceColor.WHITE,
                row=0, col=0, render_row=0.0, render_col=0.0,
                is_moving=False, is_jumping=False, rest_fraction_remaining=None,
            ),
        ],
        game_over=False,
    )


def test_a_snapshot_message_is_decoded_and_tagged_snapshot():
    client = make_client()
    snapshot = make_snapshot()
    payload = to_dict(snapshot)
    payload["clock_ms"] = 4200
    raw = json.dumps(payload)

    client._handle_message(raw)

    kind, game_snapshot, clock_ms = client.inbound.get_nowait()
    assert kind == "snapshot"
    assert game_snapshot == snapshot
    assert clock_ms == 4200


def test_an_event_message_is_decoded_and_tagged_event():
    client = make_client()
    event = MoveCompletedEvent(
        piece_id="p1", piece_kind=PieceKind.ROOK, piece_color=PieceColor.WHITE,
        destination=AT, at_ms=100,
    )
    raw = json.dumps(to_dict(event))

    client._handle_message(raw)

    kind, decoded_event = client.inbound.get_nowait()
    assert kind == "event"
    assert decoded_event == event


def test_a_different_event_type_also_decodes_correctly():
    client = make_client()
    event = CaptureEvent(
        piece_id="p1", piece_kind=PieceKind.ROOK, piece_color=PieceColor.WHITE,
        captured_piece_id="p2", captured_kind=PieceKind.PAWN, captured_color=PieceColor.BLACK,
        at=AT, at_ms=200,
    )
    raw = json.dumps(to_dict(event))

    client._handle_message(raw)

    kind, decoded_event = client.inbound.get_nowait()
    assert kind == "event"
    assert decoded_event == event


def test_a_role_message_is_decoded_and_tagged_role():
    client = make_client()
    raw = json.dumps({"type": "role", "role": "black"})

    client._handle_message(raw)

    assert client.inbound.get_nowait() == ("role", "black")


def test_multiple_messages_queue_in_order():
    client = make_client()
    snapshot = make_snapshot()
    snapshot_payload = to_dict(snapshot)
    snapshot_payload["clock_ms"] = 10
    event = MoveCompletedEvent(
        piece_id="p1", piece_kind=PieceKind.ROOK, piece_color=PieceColor.WHITE,
        destination=AT, at_ms=100,
    )

    client._handle_message(json.dumps(snapshot_payload))
    client._handle_message(json.dumps(to_dict(event)))

    first = client.inbound.get_nowait()
    second = client.inbound.get_nowait()
    assert first[0] == "snapshot"
    assert second == ("event", event)


def test_the_servers_actual_connection_sequence_decodes_cleanly():
    # server/ws_server.py sends "role" then the initial snapshot on every
    # new connection - both must decode without error, in that order.
    client = make_client()
    snapshot = make_snapshot()
    snapshot_payload = to_dict(snapshot)
    snapshot_payload["clock_ms"] = 0

    client._handle_message(json.dumps({"type": "role", "role": "white"}))
    client._handle_message(json.dumps(snapshot_payload))

    role_item = client.inbound.get_nowait()
    snapshot_item = client.inbound.get_nowait()
    assert role_item == ("role", "white")
    assert snapshot_item[0] == "snapshot"
    assert snapshot_item[1] == snapshot
