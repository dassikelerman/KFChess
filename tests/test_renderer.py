from board.text_board import TextBoardRepresentation
from game.renderer import BoardRenderer


def test_render_single_row():
    board = TextBoardRepresentation([["wK", ".", "bK"]])
    assert BoardRenderer().render(board) == "wK . bK"


def test_render_multiple_rows():
    board = TextBoardRepresentation([["wK", ".", "bK"], [".", ".", "."]])
    assert BoardRenderer().render(board) == "wK . bK\n. . ."


def test_render_empty_board():
    board = TextBoardRepresentation([])
    assert BoardRenderer().render(board) == ""


def test_render_reflects_mutations():
    board = TextBoardRepresentation([["wK", ".", "bK"]])
    board.set(0, 1, "wQ")
    assert BoardRenderer().render(board) == "wK wQ bK"
