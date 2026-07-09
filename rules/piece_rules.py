from rules.movement_strategy import MovementStrategy


def _shape_delta(dr, dc):
    return abs(dr), abs(dc)


def path_is_clear(board, start, end):
    """Shared sliding-piece helper: True if every square strictly between
    start and end is empty. Used by Rook, Bishop and Queen so the check is
    written once (DRY) instead of duplicated per piece.
    """
    sr, sc = start
    er, ec = end
    dr = (er > sr) - (er < sr)
    dc = (ec > sc) - (ec < sc)
    r, c = sr + dr, sc + dc
    while (r, c) != (er, ec):
        if not board.is_empty(r, c):
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
    start row is whichever edge it moves away from (row 0 if it advances
    downward, the last row if it advances upward).
    """

    def __init__(self, directions):
        self._directions = directions

    def is_legal(self, dr, dc, context):
        direction = self._directions[context.color]
        start_row = context.board.height - 1 if direction < 0 else 0
        sr, _sc = context.start

        if dc == 0:
            if dr == direction and not context.target_occupied:
                return True
            if sr == start_row and dr == 2 * direction and not context.target_occupied:
                mid_row = sr + direction
                return context.board.is_empty(mid_row, context.start[1])
            return False

        if abs(dc) == 1 and dr == direction and context.target_occupied:
            return True

        return False
