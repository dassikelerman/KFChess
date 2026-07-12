from dataclasses import dataclass, replace
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


class PieceState(Enum):
    IDLE = "IDLE"
    MOVING = "MOVING"
    CAPTURED = "CAPTURED"


@dataclass(frozen=True)
class Piece:
    id: str
    color: PieceColor
    kind: PieceKind
    cell: Position
    state: PieceState

    def mark_moving(self) -> "Piece":
        return replace(self, state=PieceState.MOVING)

    def mark_idle(self) -> "Piece":
        return replace(self, state=PieceState.IDLE)

    def mark_captured(self) -> "Piece":
        return replace(self, state=PieceState.CAPTURED)


def parse_kind(letter):
    """Build a PieceKind from a one-character token letter.

    Raises ValueError if the letter isn't one of PieceKind's members -
    PieceKind is the single source of truth for every piece kind Board can
    hold, so there's no fallback to a raw letter.
    """
    return PieceKind(letter)


def kind_letter(kind):
    """Inverse of parse_kind: the one-character token letter for a PieceKind."""
    return kind.value
