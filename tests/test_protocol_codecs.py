import json

import pytest

from engine.snapshot import GameSnapshot, PieceSnapshot
from events.game_events import (
    CaptureEvent,
    GameOverEvent,
    IllegalActionEvent,
    JumpCompletedEvent,
    MotionStoppedEvent,
    MoveCompletedEvent,
    PlayerDisconnectedEvent,
    PlayerReconnectedEvent,
    PromotionEvent,
)
from model.piece import PieceColor, PieceKind
from model.position import Position
from protocol.game_messages import JumpIntent, MoveIntent
from protocol.lobby_messages import (
    InvalidRoomIntentError,
    LoggedIn,
    Login,
    MatchNotFound,
    PlayIntent,
    RoomCreated,
    RoomIntent,
    RoomRejected,
)
from protocol.message_types import RoomAction
from protocol.registry import (
    UnknownMessageTypeError,
    UnregisteredMessageClassError,
    decode_json_message,
    encode_json_message,
    message_from_payload,
    message_to_payload,
)
from protocol.snapshot_codec import snapshot_to_payload

AT = Position(1, 2)

SNAPSHOT = GameSnapshot(
    board_width=8,
    board_height=8,
    pieces=[
        PieceSnapshot(
            id="wP@6,0", kind=PieceKind.PAWN, color=PieceColor.WHITE,
            row=6, col=0, render_row=6.0, render_col=0.0,
            is_moving=False, is_jumping=False, rest_fraction_remaining=None,
        ),
        PieceSnapshot(
            id="bN@0,1", kind=PieceKind.KNIGHT, color=PieceColor.BLACK,
            row=0, col=1, render_row=0.3, render_col=1.0,
            is_moving=True, is_jumping=False, rest_fraction_remaining=0.4,
        ),
    ],
    game_over=False,
)

SAMPLES = [
    SNAPSHOT,
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
    GameOverEvent(winner_color=None, at_ms=600),  # game can end without a winner
    IllegalActionEvent(piece_id="p1", destination=AT, at_ms=700),
    IllegalActionEvent(piece_id=None, destination=AT, at_ms=700),  # empty-cell attempt
    PlayerDisconnectedEvent(color=PieceColor.WHITE, seconds_remaining=15),
    PlayerReconnectedEvent(color=PieceColor.WHITE),
    MoveIntent(source=Position(0, 0), destination=AT),
    JumpIntent(position=AT),
    Login(username="alice", password="hunter2"),
    LoggedIn(username="alice", rating=1200),
    PlayIntent(),
    RoomIntent(action=RoomAction.CREATE),
    RoomIntent(action=RoomAction.JOIN, room_id="room-1"),
    RoomCreated(room_id="room-1"),
    RoomRejected(reason="room_full"),
    MatchNotFound(),
    MatchNotFound(reason="opponent_declined"),
]


@pytest.mark.parametrize("obj", SAMPLES, ids=lambda o: type(o).__name__)
def test_round_trip_through_message_to_payload_and_message_from_payload_returns_an_equal_object(obj):
    assert message_from_payload(message_to_payload(obj)) == obj


@pytest.mark.parametrize("obj", SAMPLES, ids=lambda o: type(o).__name__)
def test_round_trip_through_encode_and_decode_json_message_returns_an_equal_object(obj):
    assert decode_json_message(encode_json_message(obj)) == obj


@pytest.mark.parametrize("obj", SAMPLES, ids=lambda o: type(o).__name__)
def test_message_to_payload_output_is_json_serializable(obj):
    json.dumps(message_to_payload(obj))  # must not raise


@pytest.mark.parametrize("obj", SAMPLES, ids=lambda o: type(o).__name__)
def test_message_to_payload_tags_the_output_with_its_own_class_name(obj):
    assert message_to_payload(obj)["type"] == type(obj).__name__


def test_message_from_payload_dispatches_purely_off_the_type_key_not_caller_hints():
    payload = message_to_payload(MoveIntent(source=Position(0, 0), destination=AT))
    assert isinstance(message_from_payload(payload), MoveIntent)


def test_position_fields_serialize_as_plain_row_col_dicts():
    payload = message_to_payload(JumpIntent(position=AT))
    assert payload["position"] == {"row": 1, "col": 2}


def test_piece_colors_and_kinds_serialize_as_plain_strings():
    event = MoveCompletedEvent(
        piece_id="p1", piece_kind=PieceKind.ROOK, piece_color=PieceColor.WHITE,
        destination=AT, at_ms=100,
    )
    payload = message_to_payload(event)
    assert payload["piece_kind"] == "R"
    assert payload["piece_color"] == "w"


def test_a_full_snapshot_round_trips_through_a_real_json_string():
    wire = encode_json_message(SNAPSHOT)
    restored = decode_json_message(wire)
    assert restored == SNAPSHOT


def test_snapshot_to_payload_returns_the_snapshots_payload_form_plus_the_clock():
    payload = snapshot_to_payload(SNAPSHOT, clock_ms=1234)

    expected = message_to_payload(SNAPSHOT)
    expected["clock_ms"] = 1234
    assert payload == expected
    assert payload["type"] == "GameSnapshot"
    assert payload["clock_ms"] == 1234


def test_snapshot_to_payload_does_not_mutate_the_snapshot():
    snapshot_to_payload(SNAPSHOT, clock_ms=1234)
    assert message_to_payload(SNAPSHOT) == message_to_payload(SNAPSHOT)  # unaffected by the call above
    assert "clock_ms" not in message_to_payload(SNAPSHOT)


def test_snapshot_to_payload_is_json_serializable():
    json.dumps(snapshot_to_payload(SNAPSHOT, clock_ms=1234))  # must not raise


def test_a_room_intent_to_join_with_an_empty_room_id_is_rejected():
    payload = message_to_payload(RoomIntent(action=RoomAction.JOIN, room_id=""))
    with pytest.raises(InvalidRoomIntentError):
        message_from_payload(payload)


def test_a_room_intent_to_join_with_a_whitespace_only_room_id_is_rejected():
    payload = message_to_payload(RoomIntent(action=RoomAction.JOIN, room_id="   "))
    with pytest.raises(InvalidRoomIntentError):
        message_from_payload(payload)


def test_a_room_intent_to_join_normalizes_a_padded_room_id():
    payload = message_to_payload(RoomIntent(action=RoomAction.JOIN, room_id="  abc  "))
    assert message_from_payload(payload) == RoomIntent(action=RoomAction.JOIN, room_id="abc")


def test_a_room_intent_to_create_ignores_an_extraneous_room_id():
    payload = message_to_payload(RoomIntent(action=RoomAction.CREATE, room_id="some-id"))
    assert message_from_payload(payload) == RoomIntent(action=RoomAction.CREATE, room_id=None)


def test_an_unknown_type_raises_a_clear_error_not_a_bare_key_error():
    with pytest.raises(UnknownMessageTypeError):
        message_from_payload({"type": "SomethingMadeUp"})


def test_an_unknown_type_error_names_every_type_it_does_know():
    with pytest.raises(UnknownMessageTypeError, match="MoveIntent"):
        message_from_payload({"type": "SomethingMadeUp"})


def test_a_non_dict_payload_raises_a_clear_error_not_a_bare_attribute_error():
    with pytest.raises(UnknownMessageTypeError):
        message_from_payload("just a string, not a payload dict")


def test_an_unregistered_class_raises_a_clear_error_not_a_bare_key_error():
    class NotAMessage:
        pass

    with pytest.raises(UnregisteredMessageClassError, match="NotAMessage"):
        message_to_payload(NotAMessage())
