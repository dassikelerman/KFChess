import pytest

from board_io.board_parser import parse_input, build_board, BoardParseError
from model.piece import kind_letter
from model.position import Position

COLORS = ("w", "b")
EMPTY_CELL = "."


def get(board, row, col):
    piece = board.piece_at(Position(row, col))
    return EMPTY_CELL if piece is None else piece.color.value + kind_letter(piece.kind)


def is_empty(board, row, col):
    return board.piece_at(Position(row, col)) is None


def build(lines):
    return build_board(lines, colors=COLORS, empty_cell=EMPTY_CELL)


def test_parse_input_splits_sections():
    lines = ["Board:", "wK . bK", "Commands:", "print", "wait 5"]
    board_lines, commands = parse_input(lines)
    assert board_lines == ["wK . bK"]
    assert commands == ["print", "wait 5"]


def test_build_board_valid():
    board = build(["wK . bK"])
    assert get(board, 0, 0) == "wK"
    assert is_empty(board, 0, 1)


def test_build_board_rejects_unknown_token():
    with pytest.raises(BoardParseError):
        build(["wX . bK"])


def test_build_board_rejects_row_width_mismatch():
    with pytest.raises(BoardParseError):
        build(["wK . bK", "wK ."])


def test_build_board_skips_blank_lines():
    board = build(["wK . bK", "", "  "])
    assert board.height == 1


def test_build_board_infers_dimensions_for_multiple_rows():
    board = build(["wK . bK", ". . ."])
    assert board.width == 3
    assert board.height == 2


def test_build_board_all_blank_lines_yields_empty_board():
    board = build(["", "   ", ""])
    assert board.width == 0
    assert board.height == 0


def test_build_board_no_lines_yields_empty_board():
    board = build([])
    assert board.width == 0
    assert board.height == 0


def test_build_board_normalizes_irregular_whitespace():
    board = build(["wK   .\tbK"])
    assert board.width == 3
    assert get(board, 0, 0) == "wK"
    assert get(board, 0, 2) == "bK"


def test_build_board_accepts_all_standard_piece_kinds():
    board = build(["wK wQ wR wB wN wP"])
    for col, letter in enumerate("KQRBNP"):
        assert get(board, 0, col) == "w" + letter


def test_build_board_rejects_token_of_unregistered_kind():
    with pytest.raises(BoardParseError):
        build(["wK . bZ"])


def test_parse_input_handles_missing_commands_section():
    lines = ["Board:", "wK . bK"]
    board_lines, commands = parse_input(lines)
    assert board_lines == ["wK . bK"]
    assert commands == []


def test_parse_input_ignores_lines_outside_any_section():
    lines = ["some preamble", "Board:", "wK . bK", "Commands:", "print"]
    board_lines, commands = parse_input(lines)
    assert board_lines == ["wK . bK"]
    assert commands == ["print"]
