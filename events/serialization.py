"""Pure data <-> plain-dict conversion, step 1 of the client/server
migration (see docs/kf-chess-architecture-plan.md for the full plan -
this module is only that first step). No networking, no new
architecture: to_dict()/from_dict() turn GameSnapshot, the outward
game events (events/game_events.py), and the two client->server
intents below into plain dicts that json.dumps() can handle directly,
and back into real dataclasses again.
"""

from dataclasses import dataclass

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
from model.piece import PieceColor, PieceKind
from model.position import Position


@dataclass(frozen=True)
class MoveIntent:
    source: Position
    destination: Position


@dataclass(frozen=True)
class JumpIntent:
    position: Position


@dataclass(frozen=True)
class Login:
    username: str


# -- shared value conversions -------------------------------------------------

def _position_to_dict(position):
    return {"row": position.row, "col": position.col}


def _position_from_dict(data):
    return Position(row=data["row"], col=data["col"])


def _color_to_value(color):
    return None if color is None else color.value


def _color_from_value(value):
    return None if value is None else PieceColor(value)


# -- GameSnapshot / PieceSnapshot ---------------------------------------------

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


# -- events ---------------------------------------------------------------------

def _move_completed_fields(event):
    return {
        "piece_id": event.piece_id,
        "piece_kind": event.piece_kind.value,
        "piece_color": event.piece_color.value,
        "destination": _position_to_dict(event.destination),
        "at_ms": event.at_ms,
    }


def _move_completed_kwargs(data):
    return dict(
        piece_id=data["piece_id"],
        piece_kind=PieceKind(data["piece_kind"]),
        piece_color=PieceColor(data["piece_color"]),
        destination=_position_from_dict(data["destination"]),
        at_ms=data["at_ms"],
    )


def _capture_fields(event):
    return {
        "piece_id": event.piece_id,
        "piece_kind": event.piece_kind.value,
        "piece_color": event.piece_color.value,
        "captured_piece_id": event.captured_piece_id,
        "captured_kind": event.captured_kind.value,
        "captured_color": event.captured_color.value,
        "at": _position_to_dict(event.at),
        "at_ms": event.at_ms,
    }


def _capture_kwargs(data):
    return dict(
        piece_id=data["piece_id"],
        piece_kind=PieceKind(data["piece_kind"]),
        piece_color=PieceColor(data["piece_color"]),
        captured_piece_id=data["captured_piece_id"],
        captured_kind=PieceKind(data["captured_kind"]),
        captured_color=PieceColor(data["captured_color"]),
        at=_position_from_dict(data["at"]),
        at_ms=data["at_ms"],
    )


def _jump_completed_fields(event):
    return {
        "piece_id": event.piece_id,
        "piece_kind": event.piece_kind.value,
        "piece_color": event.piece_color.value,
        "cell": _position_to_dict(event.cell),
        "at_ms": event.at_ms,
    }


def _jump_completed_kwargs(data):
    return dict(
        piece_id=data["piece_id"],
        piece_kind=PieceKind(data["piece_kind"]),
        piece_color=PieceColor(data["piece_color"]),
        cell=_position_from_dict(data["cell"]),
        at_ms=data["at_ms"],
    )


def _motion_stopped_fields(event):
    return {
        "piece_id": event.piece_id,
        "piece_kind": event.piece_kind.value,
        "piece_color": event.piece_color.value,
        "at": _position_to_dict(event.at),
        "at_ms": event.at_ms,
    }


def _motion_stopped_kwargs(data):
    return dict(
        piece_id=data["piece_id"],
        piece_kind=PieceKind(data["piece_kind"]),
        piece_color=PieceColor(data["piece_color"]),
        at=_position_from_dict(data["at"]),
        at_ms=data["at_ms"],
    )


def _promotion_fields(event):
    return {
        "piece_id": event.piece_id,
        "piece_color": event.piece_color.value,
        "from_kind": event.from_kind.value,
        "to_kind": event.to_kind.value,
        "at": _position_to_dict(event.at),
        "at_ms": event.at_ms,
    }


def _promotion_kwargs(data):
    return dict(
        piece_id=data["piece_id"],
        piece_color=PieceColor(data["piece_color"]),
        from_kind=PieceKind(data["from_kind"]),
        to_kind=PieceKind(data["to_kind"]),
        at=_position_from_dict(data["at"]),
        at_ms=data["at_ms"],
    )


def _game_over_fields(event):
    return {
        "winner_color": _color_to_value(event.winner_color),
        "at_ms": event.at_ms,
    }


def _game_over_kwargs(data):
    return dict(
        winner_color=_color_from_value(data["winner_color"]),
        at_ms=data["at_ms"],
    )


def _illegal_action_fields(event):
    return {
        "piece_id": event.piece_id,
        "destination": _position_to_dict(event.destination),
        "at_ms": event.at_ms,
    }


def _illegal_action_kwargs(data):
    return dict(
        piece_id=data["piece_id"],
        destination=_position_from_dict(data["destination"]),
        at_ms=data["at_ms"],
    )


# -- client -> server intents ----------------------------------------------------

def _move_intent_fields(intent):
    return {
        "source": _position_to_dict(intent.source),
        "destination": _position_to_dict(intent.destination),
    }


def _move_intent_kwargs(data):
    return dict(
        source=_position_from_dict(data["source"]),
        destination=_position_from_dict(data["destination"]),
    )


def _jump_intent_fields(intent):
    return {"position": _position_to_dict(intent.position)}


def _jump_intent_kwargs(data):
    return dict(position=_position_from_dict(data["position"]))


def _login_fields(login):
    return {"username": login.username}


def _login_kwargs(data):
    return dict(username=data["username"])


# -- registry + public API -------------------------------------------------------

# type_name -> dataclass, plus the field-conversion pair for that type -
# to_dict()/from_dict() dispatch off this instead of an if/elif chain, so
# adding a future intent/event is a one-line registration, not a new branch.
_REGISTRY = {
    "GameSnapshot": (GameSnapshot, _game_snapshot_fields, _game_snapshot_kwargs),
    "MoveCompletedEvent": (MoveCompletedEvent, _move_completed_fields, _move_completed_kwargs),
    "CaptureEvent": (CaptureEvent, _capture_fields, _capture_kwargs),
    "JumpCompletedEvent": (JumpCompletedEvent, _jump_completed_fields, _jump_completed_kwargs),
    "MotionStoppedEvent": (MotionStoppedEvent, _motion_stopped_fields, _motion_stopped_kwargs),
    "PromotionEvent": (PromotionEvent, _promotion_fields, _promotion_kwargs),
    "GameOverEvent": (GameOverEvent, _game_over_fields, _game_over_kwargs),
    "IllegalActionEvent": (IllegalActionEvent, _illegal_action_fields, _illegal_action_kwargs),
    "MoveIntent": (MoveIntent, _move_intent_fields, _move_intent_kwargs),
    "JumpIntent": (JumpIntent, _jump_intent_fields, _jump_intent_kwargs),
    "Login": (Login, _login_fields, _login_kwargs),
}
_TYPE_NAME_BY_CLASS = {cls: name for name, (cls, _, _) in _REGISTRY.items()}


def to_dict(obj):
    type_name = _TYPE_NAME_BY_CLASS[type(obj)]
    _, fields_of, _ = _REGISTRY[type_name]
    data = fields_of(obj)
    data["type"] = type_name
    return data


def from_dict(data):
    cls, _, kwargs_from = _REGISTRY[data["type"]]
    return cls(**kwargs_from(data))


def snapshot_to_payload(snapshot, clock_ms):
    payload = to_dict(snapshot)
    payload["clock_ms"] = clock_ms
    return payload
