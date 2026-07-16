from abc import ABC, abstractmethod
from dataclasses import dataclass

from model.position import Position


@dataclass(frozen=True)
class MoveContext:
    # Bundled as one immutable object (instead of five loose parameters)
    # so new piece kinds can be registered without changing every call site.
    board: object  # model.board.Board
    color: str
    start: Position
    end: Position
    target_occupied: bool


class MovementStrategy(ABC):
    """A single piece kind's movement rule (Strategy pattern) - new kinds
    are supported by implementing this and registering with
    PieceRuleRegistry, no engine/parser code changes needed."""

    @abstractmethod
    def is_legal(self, dr: int, dc: int, context: MoveContext) -> bool:
        ...


def _shape_delta(dr, dc):
    return abs(dr), abs(dc)


def path_is_clear(board, start, end):
    sr, sc = start.row, start.col
    er, ec = end.row, end.col
    dr = (er > sr) - (er < sr)
    dc = (ec > sc) - (ec < sc)
    r, c = sr + dr, sc + dc
    while (r, c) != (er, ec):
        if board.piece_at(Position(r, c)) is not None:
            return False
        r += dr
        c += dc
    return True


class KingMovement(MovementStrategy):
    def is_legal(self, dr, dc, context):
        r, c = _shape_delta(dr, dc)
        return max(r, c) == 1


class RookMovement(MovementStrategy):
    def is_legal(self, dr, dc, context):
        if not ((dr == 0) != (dc == 0)):
            return False
        return path_is_clear(context.board, context.start, context.end)


class BishopMovement(MovementStrategy):
    def is_legal(self, dr, dc, context):
        r, c = _shape_delta(dr, dc)
        if not (r == c and r != 0):
            return False
        return path_is_clear(context.board, context.start, context.end)


class QueenMovement(MovementStrategy):
    def is_legal(self, dr, dc, context):
        r, c = _shape_delta(dr, dc)
        straight = (dr == 0) != (dc == 0)
        diagonal = r == c and r != 0
        if not (straight or diagonal):
            return False
        return path_is_clear(context.board, context.start, context.end)


class KnightMovement(MovementStrategy):
    def is_legal(self, dr, dc, context):
        r, c = _shape_delta(dr, dc)
        return sorted([r, c]) == [1, 2]


class PawnMovement(MovementStrategy):
    def __init__(self, directions):
        self._directions = directions

    def is_legal(self, dr, dc, context):
        # A color's start row is derived from board height rather than a
        # fixed number (boards vary in size): one row in front of its
        # back rank in its direction of travel.
        direction = self._directions[context.color]
        back_rank = context.board.height - 1 if direction < 0 else 0
        start_row = back_rank + direction
        sr = context.start.row

        if dc == 0:
            if dr == direction and not context.target_occupied:
                return True
            if sr == start_row and dr == 2 * direction and not context.target_occupied:
                mid_row = sr + direction
                return context.board.piece_at(Position(mid_row, context.start.col)) is None
            return False

        if abs(dc) == 1 and dr == direction and context.target_occupied:
            return True

        return False
