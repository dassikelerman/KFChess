from dataclasses import dataclass
from enum import Enum

from model.position import Position


class PieceColor(Enum):
    WHITE = "w"
    BLACK = "b"


class PieceKind(Enum):
    KING = "K"
    QUEEN = "Q"
    ROOK = "R"
    BISHOP = "B"
    KNIGHT = "N"
    PAWN = "P"


class AnimationState(Enum):
    """What a renderer should currently be playing for a piece - values
    match the asset folder names (pieces1/<TOKEN>/states/) exactly.

    Purely a view-side concept: GameEngine never constructs or reports an
    AnimationState. PieceSnapshot instead carries logical facts
    (is_moving/is_jumping) that a view derives IDLE/MOVE/JUMP from itself
    (see view.animation_state.derive_animation_state); LONG_REST/
    SHORT_REST are layered on top of that by view.piece_state_machine.
    PieceStateMachine, without the engine needing to track "how long ago"
    anything happened.
    """

    IDLE = "idle"
    MOVE = "move"
    JUMP = "jump"
    LONG_REST = "long_rest"
    SHORT_REST = "short_rest"


@dataclass(frozen=True)
class Piece:
    id: str
    color: PieceColor
    kind: PieceKind
    cell: Position


def parse_kind(letter):
    return PieceKind(letter)


def kind_letter(kind):
    return kind.value
