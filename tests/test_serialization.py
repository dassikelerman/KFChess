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
    PromotionEvent,
)
from protocol.serialization import JumpIntent, Login, MoveIntent, from_dict, snapshot_to_payload, to_dict
from model.piece import PieceColor, PieceKind
from model.position import Position

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
    MoveIntent(source=Position(0, 0), destination=AT),
    JumpIntent(position=AT),
    Login(username="alice", password="hunter2"),
]


@pytest.mark.parametrize("obj", SAMPLES, ids=lambda o: type(o).__name__)
def test_round_trip_through_to_dict_and_from_dict_returns_an_equal_object(obj):
    assert from_dict(to_dict(obj)) == obj


@pytest.mark.parametrize("obj", SAMPLES, ids=lambda o: type(o).__name__)
def test_to_dict_output_is_json_serializable(obj):
    json.dumps(to_dict(obj))  # must not raise


@pytest.mark.parametrize("obj", SAMPLES, ids=lambda o: type(o).__name__)
def test_to_dict_tags_the_output_with_its_own_class_name(obj):
    assert to_dict(obj)["type"] == type(obj).__name__


def test_from_dict_dispatches_purely_off_the_type_key_not_caller_hints():
    data = to_dict(MoveIntent(source=Position(0, 0), destination=AT))
    assert isinstance(from_dict(data), MoveIntent)


def test_position_fields_serialize_as_plain_row_col_dicts():
    data = to_dict(JumpIntent(position=AT))
    assert data["position"] == {"row": 1, "col": 2}


def test_piece_colors_and_kinds_serialize_as_plain_strings():
    event = MoveCompletedEvent(
        piece_id="p1", piece_kind=PieceKind.ROOK, piece_color=PieceColor.WHITE,
        destination=AT, at_ms=100,
    )
    data = to_dict(event)
    assert data["piece_kind"] == "R"
    assert data["piece_color"] == "w"


def test_a_full_snapshot_round_trips_through_a_real_json_string():
    wire = json.dumps(to_dict(SNAPSHOT))
    restored = from_dict(json.loads(wire))
    assert restored == SNAPSHOT


def test_snapshot_to_payload_returns_the_snapshots_to_dict_form_plus_the_clock():
    payload = snapshot_to_payload(SNAPSHOT, clock_ms=1234)

    expected = to_dict(SNAPSHOT)
    expected["clock_ms"] = 1234
    assert payload == expected
    assert payload["type"] == "GameSnapshot"
    assert payload["clock_ms"] == 1234


def test_snapshot_to_payload_does_not_mutate_the_snapshot():
    snapshot_to_payload(SNAPSHOT, clock_ms=1234)
    assert to_dict(SNAPSHOT) == to_dict(SNAPSHOT)  # unaffected by the call above
    assert "clock_ms" not in to_dict(SNAPSHOT)


def test_snapshot_to_payload_is_json_serializable():
    json.dumps(snapshot_to_payload(SNAPSHOT, clock_ms=1234))  # must not raise
