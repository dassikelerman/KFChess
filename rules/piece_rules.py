from abc import ABC, abstractmethod
from dataclasses import dataclass

from model.position import Position


@dataclass(frozen=True)
class MoveContext:
    """Everything a movement strategy needs to judge a move, bundled up.

    Keeping this as one immutable object (instead of passing five loose
    parameters around) is what lets new piece kinds be registered without
    changing every call site.
    """

    board: object  # model.board.Board
    color: str
    start: Position
    end: Position
    target_occupied: bool


class MovementStrategy(ABC):
    """A single piece kind's movement rule (Strategy pattern).

    New movement rules for any PieceKind are supported simply by
    implementing this interface and registering an instance with a
    PieceRuleRegistry. No engine or parser code needs to change.
    """

    @abstractmethod
    def is_legal(self, dr: int, dc: int, context: MoveContext) -> bool:
        ...


def _shape_delta(dr, dc):
    return abs(dr), abs(dc)


def path_is_clear(board, start, end):
    """Shared sliding-piece helper: True if every square strictly between
    start and end is empty. Used by Rook, Bishop and Queen so the check is
    written once (DRY) instead of duplicated per piece.
    """
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
    """Pawn behaviour depends on per-color direction, which is injected
    rather than hardcoded, so board layouts or custom variants can change
    it without editing this class.

    A pawn's start row is derived from the board's own height rather than
    a fixed number, since boards in this game vary in size: a color's
    start row is one row in front of its back rank (row 1 if it advances
    downward, one row short of the last row if it advances upward) - pawns
    never start on the back rank itself, that's where the other pieces sit.
    """

    def __init__(self, directions):
        self._directions = directions

    def is_legal(self, dr, dc, context):
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
