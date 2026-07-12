import pytest

from board_io.board_parser import parse_input, build_board, BoardParseError
from model.piece import kind_letter
from model.position import Position
from rules.rule_engine import build_default_registry

COLORS = ("w", "b")
EMPTY_CELL = "."


def get(board, row, col):
    piece = board.piece_at(Position(row, col))
    return EMPTY_CELL if piece is None else piece.color.value + kind_letter(piece.kind)


def is_empty(board, row, col):
    return board.piece_at(Position(row, col)) is None


def build(lines, registry):
    return build_board(lines, registry, colors=COLORS, empty_cell=EMPTY_CELL)


@pytest.fixture
def registry():
    return build_default_registry(pawn_direction={"w": -1, "b": 1})


def test_parse_input_splits_sections():
    lines = ["Board:", "wK . bK", "Commands:", "print", "wait 5"]
    board_lines, commands = parse_input(lines)
    assert board_lines == ["wK . bK"]
    assert commands == ["print", "wait 5"]


def test_build_board_valid(registry):
    board = build(["wK . bK"], registry)
    assert get(board, 0, 0) == "wK"
    assert is_empty(board, 0, 1)


def test_build_board_rejects_unknown_token(registry):
    with pytest.raises(BoardParseError):
        build(["wX . bK"], registry)


def test_build_board_rejects_row_width_mismatch(registry):
    with pytest.raises(BoardParseError):
        build(["wK . bK", "wK ."], registry)


def test_build_board_skips_blank_lines(registry):
    board = build(["wK . bK", "", "  "], registry)
    assert board.height == 1


def test_build_board_infers_dimensions_for_multiple_rows(registry):
    board = build(["wK . bK", ". . ."], registry)
    assert board.width == 3
    assert board.height == 2


def test_build_board_all_blank_lines_yields_empty_board(registry):
    board = build(["", "   ", ""], registry)
    assert board.width == 0
    assert board.height == 0


def test_build_board_no_lines_yields_empty_board(registry):
    board = build([], registry)
    assert board.width == 0
    assert board.height == 0


def test_build_board_normalizes_irregular_whitespace(registry):
    board = build(["wK   .\tbK"], registry)
    assert board.width == 3
    assert get(board, 0, 0) == "wK"
    assert get(board, 0, 2) == "bK"


def test_build_board_derives_valid_tokens_from_registered_kinds():
    from model.piece import PieceKind
    from rules.rule_engine import PieceRuleRegistry
    from rules.piece_rules import MovementStrategy

    class DummyStrategy(MovementStrategy):
        def is_legal(self, dr, dc, context):
            return True

    partial_registry = PieceRuleRegistry()
    partial_registry.register(PieceKind.QUEEN, DummyStrategy())

    board = build(["wQ . bQ"], partial_registry)
    assert get(board, 0, 0) == "wQ"
    assert get(board, 0, 2) == "bQ"

    with pytest.raises(BoardParseError):
        build(["wQ . bK"], partial_registry)


def test_build_board_rejects_token_of_unregistered_kind(registry):
    with pytest.raises(BoardParseError):
        build(["wK . bZ"], registry)


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
