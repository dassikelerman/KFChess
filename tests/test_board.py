from model.board import Board
from model.piece import Piece, PieceColor, PieceKind
from model.position import Position


def make_piece(token, row, col):
    return Piece(
        id=f"{token}@{row},{col}",
        color=PieceColor(token[0]),
        kind=PieceKind(token[1]),
        cell=Position(row, col),
    )


def make_board():
    return Board([["wK", ".", "bK"], [".", ".", "."]])


def test_dimensions():
    board = make_board()
    assert board.width == 3
    assert board.height == 2


def test_get_set():
    board = make_board()
    piece = make_piece("wQ", 1, 1)
    board.add_piece(piece)
    assert board.piece_at(Position(1, 1)) == piece


def test_remove_piece_by_stale_object_does_not_delete_the_new_occupant():
    # A caller might hold onto a Piece object after the cell it names has
    # since been taken over by a different piece (e.g. captured and
    # replaced). remove_piece(Piece) must key off the piece's own id, not
    # blindly trust piece.cell, or it would delete whatever is *currently*
    # sitting there instead of the (already-gone) piece it was asked to
    # remove.
    board = make_board()
    old_piece = make_piece("wQ", 1, 1)
    board.add_piece(old_piece)
    new_piece = make_piece("bN", 1, 1)  # takes over the same cell
    board.add_piece(new_piece)

    board.remove_piece(old_piece)  # stale reference to the piece no longer there

    assert board.piece_at(Position(1, 1)) == new_piece


def test_is_empty():
    board = make_board()
    assert board.piece_at(Position(0, 1)) is None
    assert board.piece_at(Position(0, 0)) is not None


def test_in_bounds():
    board = make_board()
    assert board.in_bounds(Position(0, 0)) is True
    assert board.in_bounds(Position(2, 0)) is False
    assert board.in_bounds(Position(0, -1)) is False


def test_snapshot_is_a_copy():
    board = make_board()
    snap = board.snapshot()
    snap[0][0] = "bQ"
    piece = board.piece_at(Position(0, 0))
    assert piece.color == PieceColor.WHITE
    assert piece.kind == PieceKind.KING


def test_empty_board_dimensions():
    board = Board([])
    assert board.width == 0
    assert board.height == 0


def test_single_cell_board_dimensions():
    board = Board([["wK"]])
    assert board.width == 1
    assert board.height == 1


def test_single_column_board_dimensions():
    board = Board([["wK"], ["."], ["bK"]])
    assert board.width == 1
    assert board.height == 3
