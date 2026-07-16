from dataclasses import dataclass
from typing import List, Optional

from model.piece import PieceColor


@dataclass(frozen=True)
class PieceSnapshot:
    # row/col is the piece's logical cell; an in-flight piece still
    # reports its source here until it actually lands. render_row/
    # render_col is the interpolated visual position (see
    # GameEngine._interpolated_position).
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
