import pytest

from model.board import TextBoardRepresentation
from rules.piece_rules import (
    MoveContext,
    KingMovement, QueenMovement, RookMovement,
    BishopMovement, KnightMovement, PawnMovement,
)


def context(board, color, start, end):
    return MoveContext(
        board=board,
        color=color,
        start=start,
        end=end,
        target_occupied=not board.is_empty(*end),
    )


def empty_board(width=8, height=8):
    return TextBoardRepresentation([["."] * width for _ in range(height)])


def test_king_moves_one_square_any_direction():
    board = empty_board()
    king = KingMovement()
    assert king.is_legal(1, 1, context(board, "w", (4, 4), (5, 5)))
    assert not king.is_legal(2, 0, context(board, "w", (4, 4), (6, 4)))


def test_king_rejects_null_move():
    board = empty_board()
    king = KingMovement()
    assert not king.is_legal(0, 0, context(board, "w", (4, 4), (4, 4)))


def test_rook_blocked_by_piece():
    board = empty_board()
    board.set(4, 6, "bP")
    rook = RookMovement()
    assert not rook.is_legal(0, 4, context(board, "w", (4, 4), (4, 8 - 1)))


def test_rook_clear_path():
    board = empty_board()
    rook = RookMovement()
    assert rook.is_legal(0, 3, context(board, "w", (4, 4), (4, 7)))


def test_rook_rejects_diagonal_move():
    board = empty_board()
    rook = RookMovement()
    assert not rook.is_legal(3, 3, context(board, "w", (4, 4), (7, 7)))


def test_bishop_requires_diagonal():
    board = empty_board()
    bishop = BishopMovement()
    assert bishop.is_legal(2, 2, context(board, "w", (2, 2), (4, 4)))
    assert not bishop.is_legal(2, 3, context(board, "w", (2, 2), (4, 5)))


def test_bishop_blocked_by_piece():
    board = empty_board()
    board.set(3, 3, "bP")
    bishop = BishopMovement()
    assert not bishop.is_legal(2, 2, context(board, "w", (2, 2), (4, 4)))


def test_queen_moves_straight_or_diagonal():
    board = empty_board()
    queen = QueenMovement()
    assert queen.is_legal(0, 3, context(board, "w", (0, 0), (0, 3)))
    assert queen.is_legal(3, 3, context(board, "w", (0, 0), (3, 3)))
    assert not queen.is_legal(3, 1, context(board, "w", (0, 0), (3, 1)))


def test_queen_blocked_by_piece():
    board = empty_board()
    board.set(0, 2, "bP")
    queen = QueenMovement()
    assert not queen.is_legal(0, 3, context(board, "w", (0, 0), (0, 3)))


def test_knight_l_shape():
    board = empty_board()
    knight = KnightMovement()
    assert knight.is_legal(2, 1, context(board, "w", (0, 0), (2, 1)))
    assert not knight.is_legal(2, 2, context(board, "w", (0, 0), (2, 2)))


def test_knight_rejects_straight_move():
    board = empty_board()
    knight = KnightMovement()
    assert not knight.is_legal(0, 3, context(board, "w", (0, 0), (0, 3)))


def test_knight_ignores_blockers():
    board = empty_board()
    board.set(1, 0, "wP")
    board.set(1, 1, "bP")
    knight = KnightMovement()
    assert knight.is_legal(2, 1, context(board, "w", (0, 0), (2, 1)))


def test_pawn_single_step_forward():
    board = empty_board()
    pawn = PawnMovement({"w": -1, "b": 1})
    assert pawn.is_legal(-1, 0, context(board, "w", (6, 4), (5, 4)))


def test_pawn_double_step_requires_clear_path_and_start_row():
    board = empty_board()
    pawn = PawnMovement({"w": -1, "b": 1})
    # white's start row is the board's last row (board height 8 -> row 7)
    assert pawn.is_legal(-2, 0, context(board, "w", (7, 4), (5, 4)))

    board.set(6, 4, "bP")
    assert not pawn.is_legal(-2, 0, context(board, "w", (7, 4), (5, 4)))


def test_pawn_cannot_move_two_cells_off_the_start_row():
    board = empty_board()
    pawn = PawnMovement({"w": -1, "b": 1})
    # row 5 is not white's start row (row 7), even though the path is clear
    assert not pawn.is_legal(-2, 0, context(board, "w", (5, 4), (3, 4)))


def test_pawn_cannot_capture_forward():
    board = empty_board()
    board.set(5, 4, "bP")
    pawn = PawnMovement({"w": -1, "b": 1})
    assert not pawn.is_legal(-1, 0, context(board, "w", (6, 4), (5, 4)))


def test_pawn_diagonal_capture_only_when_occupied():
    board = empty_board()
    pawn = PawnMovement({"w": -1, "b": 1})
    assert not pawn.is_legal(-1, 1, context(board, "w", (6, 4), (5, 5)))

    board.set(5, 5, "bP")
    assert pawn.is_legal(-1, 1, context(board, "w", (6, 4), (5, 5)))


def test_black_pawn_single_step_forward():
    board = empty_board()
    pawn = PawnMovement({"w": -1, "b": 1})
    assert pawn.is_legal(1, 0, context(board, "b", (1, 4), (2, 4)))
    assert not pawn.is_legal(-1, 0, context(board, "b", (1, 4), (0, 4)))  # wrong direction


def test_black_pawn_double_step_requires_clear_path_and_start_row():
    board = empty_board()
    pawn = PawnMovement({"w": -1, "b": 1})
    # black's start row is row 0 regardless of board height
    assert pawn.is_legal(2, 0, context(board, "b", (0, 4), (2, 4)))

    board.set(1, 4, "wP")
    assert not pawn.is_legal(2, 0, context(board, "b", (0, 4), (2, 4)))

    # not legal once the pawn is off its start row, even with a clear path
    assert not pawn.is_legal(2, 0, context(board, "b", (1, 4), (3, 4)))


def test_black_pawn_diagonal_capture_only_when_occupied():
    board = empty_board()
    pawn = PawnMovement({"w": -1, "b": 1})
    assert not pawn.is_legal(1, 1, context(board, "b", (1, 4), (2, 5)))

    board.set(2, 5, "wP")
    assert pawn.is_legal(1, 1, context(board, "b", (1, 4), (2, 5)))


def test_black_pawn_cannot_capture_forward():
    board = empty_board()
    board.set(2, 4, "wP")
    pawn = PawnMovement({"w": -1, "b": 1})
    assert not pawn.is_legal(1, 0, context(board, "b", (1, 4), (2, 4)))
