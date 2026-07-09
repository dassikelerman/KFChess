import pytest

from config import settings
from game.parser import parse_input, build_board, BoardParseError
from rules.rule_registry import build_default_registry


@pytest.fixture
def registry():
    return build_default_registry(settings)


def test_parse_input_splits_sections():
    lines = ["Board:", "wK . bK", "Commands:", "print", "wait 5"]
    board_lines, commands = parse_input(lines)
    assert board_lines == ["wK . bK"]
    assert commands == ["print", "wait 5"]


def test_build_board_valid(registry):
    board = build_board(["wK . bK"], registry, settings)
    assert board.get(0, 0) == "wK"
    assert board.is_empty(0, 1)


def test_build_board_rejects_unknown_token(registry):
    with pytest.raises(BoardParseError):
        build_board(["wX . bK"], registry, settings)


def test_build_board_rejects_row_width_mismatch(registry):
    with pytest.raises(BoardParseError):
        build_board(["wK . bK", "wK ."], registry, settings)


def test_build_board_skips_blank_lines(registry):
    board = build_board(["wK . bK", "", "  "], registry, settings)
    assert board.height == 1


def test_build_board_infers_dimensions_for_multiple_rows(registry):
    board = build_board(["wK . bK", ". . ."], registry, settings)
    assert board.width == 3
    assert board.height == 2


def test_build_board_all_blank_lines_yields_empty_board(registry):
    board = build_board(["", "   ", ""], registry, settings)
    assert board.width == 0
    assert board.height == 0


def test_build_board_no_lines_yields_empty_board(registry):
    board = build_board([], registry, settings)
    assert board.width == 0
    assert board.height == 0


def test_build_board_normalizes_irregular_whitespace(registry):
    board = build_board(["wK   .\tbK"], registry, settings)
    assert board.width == 3
    assert board.get(0, 0) == "wK"
    assert board.get(0, 2) == "bK"


def test_build_board_accepts_custom_registered_piece_kind():
    from rules.rule_registry import PieceRuleRegistry
    from rules.movement_strategy import MovementStrategy

    class DummyStrategy(MovementStrategy):
        def is_legal(self, dr, dc, context):
            return True

    custom_registry = PieceRuleRegistry()
    custom_registry.register("C", DummyStrategy())

    board = build_board(["wC . bC"], custom_registry, settings)
    assert board.get(0, 0) == "wC"
    assert board.get(0, 2) == "bC"


def test_build_board_rejects_token_of_unregistered_kind(registry):
    with pytest.raises(BoardParseError):
        build_board(["wK . bZ"], registry, settings)


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
