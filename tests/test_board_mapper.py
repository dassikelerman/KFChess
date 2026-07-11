import types

from model.board import TextBoardRepresentation
from input.board_mapper import pixel_to_cell


def make_board(width=3, height=3):
    return TextBoardRepresentation([["."] * width for _ in range(height)])


def config(cell_size=100):
    return types.SimpleNamespace(CELL_SIZE=cell_size)


def test_pixel_to_cell_matches_spec_examples():
    board = make_board()
    assert pixel_to_cell(50, 50, board, config()) == (0, 0)
    assert pixel_to_cell(150, 50, board, config()) == (0, 1)


def test_pixel_to_cell_out_of_bounds_returns_none():
    board = make_board()
    assert pixel_to_cell(-1, -1, board, config()) is None
    assert pixel_to_cell(1000, 1000, board, config()) is None


def test_pixel_to_cell_at_exact_cell_boundary():
    board = make_board()
    # x=100,y=0 is exactly the start of column 1, row 0
    assert pixel_to_cell(100, 0, board, config()) == (0, 1)


def test_pixel_to_cell_respects_custom_cell_size():
    board = make_board()
    assert pixel_to_cell(25, 25, board, config(cell_size=50)) == (0, 0)
    assert pixel_to_cell(75, 25, board, config(cell_size=50)) == (0, 1)
