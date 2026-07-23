"""In-game wire messages: the client's move/jump intents.

MoveIntent and JumpIntent are the only messages GameSession itself ever receives -
everything else is connection/lobby bookkeeping (see lobby_messages.py).
"""

from dataclasses import dataclass

from model.position import Position
from protocol.registry import register
from protocol.snapshot_codec import position_from_dict, position_to_dict


@dataclass(frozen=True)
class MoveIntent:
    source: Position
    destination: Position


@dataclass(frozen=True)
class JumpIntent:
    position: Position


def _move_intent_fields(intent):
    return {
        "source": position_to_dict(intent.source),
        "destination": position_to_dict(intent.destination),
    }


def _move_intent_kwargs(data):
    return dict(
        source=position_from_dict(data["source"]),
        destination=position_from_dict(data["destination"]),
    )


def _jump_intent_fields(intent):
    return {"position": position_to_dict(intent.position)}


def _jump_intent_kwargs(data):
    return dict(position=position_from_dict(data["position"]))


register("MoveIntent", MoveIntent, _move_intent_fields, _move_intent_kwargs)
register("JumpIntent", JumpIntent, _jump_intent_fields, _jump_intent_kwargs)
