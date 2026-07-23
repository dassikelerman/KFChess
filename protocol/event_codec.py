"""Codec for the domain events GameSession publishes on its dispatcher - the observable
things that happen during a game (a move landed, a capture, a promotion, someone
disconnected...). NetworkPublisher is the only thing that encodes these; the server
never needs to decode one back.
"""

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
from protocol.registry import register
from protocol.snapshot_codec import color_from_value, color_to_value, position_from_dict, position_to_dict


def _move_completed_fields(event):
    return {
        "piece_id": event.piece_id,
        "piece_kind": event.piece_kind.value,
        "piece_color": event.piece_color.value,
        "destination": position_to_dict(event.destination),
        "at_ms": event.at_ms,
    }


def _move_completed_kwargs(data):
    return dict(
        piece_id=data["piece_id"],
        piece_kind=PieceKind(data["piece_kind"]),
        piece_color=PieceColor(data["piece_color"]),
        destination=position_from_dict(data["destination"]),
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
        "at": position_to_dict(event.at),
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
        at=position_from_dict(data["at"]),
        at_ms=data["at_ms"],
    )


def _jump_completed_fields(event):
    return {
        "piece_id": event.piece_id,
        "piece_kind": event.piece_kind.value,
        "piece_color": event.piece_color.value,
        "cell": position_to_dict(event.cell),
        "at_ms": event.at_ms,
    }


def _jump_completed_kwargs(data):
    return dict(
        piece_id=data["piece_id"],
        piece_kind=PieceKind(data["piece_kind"]),
        piece_color=PieceColor(data["piece_color"]),
        cell=position_from_dict(data["cell"]),
        at_ms=data["at_ms"],
    )


def _motion_stopped_fields(event):
    return {
        "piece_id": event.piece_id,
        "piece_kind": event.piece_kind.value,
        "piece_color": event.piece_color.value,
        "at": position_to_dict(event.at),
        "at_ms": event.at_ms,
    }


def _motion_stopped_kwargs(data):
    return dict(
        piece_id=data["piece_id"],
        piece_kind=PieceKind(data["piece_kind"]),
        piece_color=PieceColor(data["piece_color"]),
        at=position_from_dict(data["at"]),
        at_ms=data["at_ms"],
    )


def _promotion_fields(event):
    return {
        "piece_id": event.piece_id,
        "piece_color": event.piece_color.value,
        "from_kind": event.from_kind.value,
        "to_kind": event.to_kind.value,
        "at": position_to_dict(event.at),
        "at_ms": event.at_ms,
    }


def _promotion_kwargs(data):
    return dict(
        piece_id=data["piece_id"],
        piece_color=PieceColor(data["piece_color"]),
        from_kind=PieceKind(data["from_kind"]),
        to_kind=PieceKind(data["to_kind"]),
        at=position_from_dict(data["at"]),
        at_ms=data["at_ms"],
    )


def _game_over_fields(event):
    return {
        "winner_color": color_to_value(event.winner_color),
        "at_ms": event.at_ms,
    }


def _game_over_kwargs(data):
    return dict(
        winner_color=color_from_value(data["winner_color"]),
        at_ms=data["at_ms"],
    )


def _illegal_action_fields(event):
    return {
        "piece_id": event.piece_id,
        "destination": position_to_dict(event.destination),
        "at_ms": event.at_ms,
    }


def _illegal_action_kwargs(data):
    return dict(
        piece_id=data["piece_id"],
        destination=position_from_dict(data["destination"]),
        at_ms=data["at_ms"],
    )


def _player_disconnected_fields(event):
    return {"color": event.color.value, "seconds_remaining": event.seconds_remaining}


def _player_disconnected_kwargs(data):
    return dict(color=PieceColor(data["color"]), seconds_remaining=data["seconds_remaining"])


def _player_reconnected_fields(event):
    return {"color": event.color.value}


def _player_reconnected_kwargs(data):
    return dict(color=PieceColor(data["color"]))


register("MoveCompletedEvent", MoveCompletedEvent, _move_completed_fields, _move_completed_kwargs)
register("CaptureEvent", CaptureEvent, _capture_fields, _capture_kwargs)
register("JumpCompletedEvent", JumpCompletedEvent, _jump_completed_fields, _jump_completed_kwargs)
register("MotionStoppedEvent", MotionStoppedEvent, _motion_stopped_fields, _motion_stopped_kwargs)
register("PromotionEvent", PromotionEvent, _promotion_fields, _promotion_kwargs)
register("GameOverEvent", GameOverEvent, _game_over_fields, _game_over_kwargs)
register("IllegalActionEvent", IllegalActionEvent, _illegal_action_fields, _illegal_action_kwargs)
register(
    "PlayerDisconnectedEvent", PlayerDisconnectedEvent,
    _player_disconnected_fields, _player_disconnected_kwargs,
)
register(
    "PlayerReconnectedEvent", PlayerReconnectedEvent,
    _player_reconnected_fields, _player_reconnected_kwargs,
)
