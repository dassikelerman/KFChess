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

    Falls back to the raw letter for custom kinds registered directly with
    a PieceRuleRegistry (e.g. "C" for a variant's "Champion" piece) - the
    registry has always accepted arbitrary kind letters, so Board must be
    able to hold pieces of a kind PieceKind doesn't know about.
    """
    try:
        return PieceKind(letter)
    except ValueError:
        return letter


def kind_letter(kind):
    """Inverse of parse_kind: the one-character token letter for a kind,
    whether it's a standard PieceKind or a custom kind letter."""
    return kind.value if isinstance(kind, PieceKind) else kind
