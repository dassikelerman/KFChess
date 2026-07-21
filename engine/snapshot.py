from dataclasses import dataclass
from typing import List, Optional

from model.piece import PieceColor


@dataclass(frozen=True)
class PieceSnapshot:
    id: str
    kind: object
    color: PieceColor
    row: int
    col: int
    render_row: float
    render_col: float
    is_moving: bool
    is_jumping: bool
    rest_fraction_remaining: Optional[float]


@dataclass(frozen=True)
class GameSnapshot:
    board_width: int
    board_height: int
    pieces: List[PieceSnapshot]
    game_over: bool
