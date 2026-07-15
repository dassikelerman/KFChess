from dataclasses import replace

from model.piece import Piece, PieceColor, kind_letter, parse_kind
from model.position import Position


class Board:
    """Stores each cell as a typed Piece (or nothing), keyed by Position.

    Game logic talks to Piece/Position objects instead of "wK"/"." strings.
    snapshot() still renders the same text tokens for callers that need them.
    """

    def __init__(self, rows=(), empty_token="."):
        self._height = len(rows)
        self._width = len(rows[0]) if rows else 0
        self._empty_token = empty_token
        self._cells = {}
        for row_index, row in enumerate(rows):
            for col_index, token in enumerate(row):
                if token == empty_token:
                    continue
                pos = Position(row_index, col_index)
                self.add_piece(
                    Piece(
                        id=f"{token}@{row_index},{col_index}",
                        color=PieceColor(token[0]),
                        kind=parse_kind(token[1]),
                        cell=pos,
                    )
                )

    @property
    def width(self):
        return self._width

    @property
    def height(self):
        return self._height

    def in_bounds(self, pos):
        return 0 <= pos.row < self._height and 0 <= pos.col < self._width

    def piece_at(self, pos):
        return self._cells.get(pos)

    def add_piece(self, piece):
        self._cells[piece.cell] = piece

    def remove_piece(self, piece_or_id):
        if isinstance(piece_or_id, Piece):
            self.remove_piece(piece_or_id.id)
            return
        position = next(
            (pos for pos, piece in self._cells.items() if piece.id == piece_or_id), None
        )
        if position is not None:
            del self._cells[position]

    def move_piece(self, piece, destination):
        self.remove_piece(piece)
        self.add_piece(replace(piece, cell=destination))

    def pieces(self):
        return list(self._cells.values())

    def snapshot(self):
        grid = [[self._empty_token] * self._width for _ in range(self._height)]
        for pos, piece in self._cells.items():
            grid[pos.row][pos.col] = piece.color.value + kind_letter(piece.kind)
        return grid
