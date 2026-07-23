import json

from client.server_connection import EventReceived, RoleAssigned, ServerConnection, SnapshotReceived
from engine.snapshot import GameSnapshot, PieceSnapshot
from events.game_events import CaptureEvent, MoveCompletedEvent
from protocol.registry import message_to_payload
from model.piece import PieceColor, PieceKind
from model.position import Position

AT = Position(1, 2)


def make_client():
    return ServerConnection("ws://unused")


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
    payload = message_to_payload(snapshot)
    payload["clock_ms"] = 4200
    raw = json.dumps(payload)

    client._handle_message(raw)

    item = client.inbound.get_nowait()
    assert isinstance(item, SnapshotReceived)
    assert item.game_snapshot == snapshot
    assert item.clock_ms == 4200


def test_an_event_message_is_decoded_and_tagged_event():
    client = make_client()
    event = MoveCompletedEvent(
        piece_id="p1", piece_kind=PieceKind.ROOK, piece_color=PieceColor.WHITE,
        destination=AT, at_ms=100,
    )
    raw = json.dumps(message_to_payload(event))

    client._handle_message(raw)

    item = client.inbound.get_nowait()
    assert isinstance(item, EventReceived)
    assert item.event == event


def test_a_different_event_type_also_decodes_correctly():
    client = make_client()
    event = CaptureEvent(
        piece_id="p1", piece_kind=PieceKind.ROOK, piece_color=PieceColor.WHITE,
        captured_piece_id="p2", captured_kind=PieceKind.PAWN, captured_color=PieceColor.BLACK,
        at=AT, at_ms=200,
    )
    raw = json.dumps(message_to_payload(event))

    client._handle_message(raw)

    item = client.inbound.get_nowait()
    assert isinstance(item, EventReceived)
    assert item.event == event


def test_a_role_message_is_decoded_and_tagged_role():
    client = make_client()
    raw = json.dumps({"type": "role", "role": "black"})

    client._handle_message(raw)

    assert client.inbound.get_nowait() == RoleAssigned(role="black")


def test_multiple_messages_queue_in_order():
    client = make_client()
    snapshot = make_snapshot()
    snapshot_payload = message_to_payload(snapshot)
    snapshot_payload["clock_ms"] = 10
    event = MoveCompletedEvent(
        piece_id="p1", piece_kind=PieceKind.ROOK, piece_color=PieceColor.WHITE,
        destination=AT, at_ms=100,
    )

    client._handle_message(json.dumps(snapshot_payload))
    client._handle_message(json.dumps(message_to_payload(event)))

    first = client.inbound.get_nowait()
    second = client.inbound.get_nowait()
    assert isinstance(first, SnapshotReceived)
    assert second == EventReceived(event=event)


def test_the_servers_actual_connection_sequence_decodes_cleanly():
    # server/ws_server.py sends "role" then the initial snapshot on every
    # new connection - both must decode without error, in that order.
    client = make_client()
    snapshot = make_snapshot()
    snapshot_payload = message_to_payload(snapshot)
    snapshot_payload["clock_ms"] = 0

    client._handle_message(json.dumps({"type": "role", "role": "white"}))
    client._handle_message(json.dumps(snapshot_payload))

    role_item = client.inbound.get_nowait()
    snapshot_item = client.inbound.get_nowait()
    assert role_item == RoleAssigned(role="white")
    assert isinstance(snapshot_item, SnapshotReceived)
    assert snapshot_item.game_snapshot == snapshot
