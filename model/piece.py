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
