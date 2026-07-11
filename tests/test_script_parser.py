from texttests.script_parser import parse_input


def test_parse_input_splits_sections():
    lines = ["Board:", "wK . bK", "Commands:", "print", "wait 5"]
    board_lines, commands = parse_input(lines)
    assert board_lines == ["wK . bK"]
    assert commands == ["print", "wait 5"]


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
