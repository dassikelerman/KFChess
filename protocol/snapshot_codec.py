"""Codec for GameSnapshot/PieceSnapshot - the board state broadcast every tick.

Also owns position_to_dict/position_from_dict and color_to_value/color_from_value:
small, shared primitives that event_codec.py reuses, since positions and colors appear
in both game state and domain events.
"""

from engine.snapshot import GameSnapshot, PieceSnapshot
from model.piece import PieceColor, PieceKind
from model.position import Position
from protocol.registry import message_to_payload, register


def position_to_dict(position):
    return {"row": position.row, "col": position.col}


def position_from_dict(data):
    return Position(row=data["row"], col=data["col"])


def color_to_value(color):
    return None if color is None else color.value


def color_from_value(value):
    return None if value is None else PieceColor(value)


def _piece_snapshot_to_dict(piece):
    return {
        "id": piece.id,
        "kind": piece.kind.value,
        "color": piece.color.value,
        "row": piece.row,
        "col": piece.col,
        "render_row": piece.render_row,
        "render_col": piece.render_col,
        "is_moving": piece.is_moving,
        "is_jumping": piece.is_jumping,
        "rest_fraction_remaining": piece.rest_fraction_remaining,
    }


def _piece_snapshot_from_dict(data):
    return PieceSnapshot(
        id=data["id"],
        kind=PieceKind(data["kind"]),
        color=PieceColor(data["color"]),
        row=data["row"],
        col=data["col"],
        render_row=data["render_row"],
        render_col=data["render_col"],
        is_moving=data["is_moving"],
        is_jumping=data["is_jumping"],
        rest_fraction_remaining=data["rest_fraction_remaining"],
    )


def _game_snapshot_fields(snapshot):
    return {
        "board_width": snapshot.board_width,
        "board_height": snapshot.board_height,
        "pieces": [_piece_snapshot_to_dict(p) for p in snapshot.pieces],
        "game_over": snapshot.game_over,
    }


def _game_snapshot_kwargs(data):
    return dict(
        board_width=data["board_width"],
        board_height=data["board_height"],
        pieces=[_piece_snapshot_from_dict(p) for p in data["pieces"]],
        game_over=data["game_over"],
    )


register("GameSnapshot", GameSnapshot, _game_snapshot_fields, _game_snapshot_kwargs)


def snapshot_to_payload(snapshot, clock_ms):
    payload = message_to_payload(snapshot)
    payload["clock_ms"] = clock_ms
    return payload
