import text.run as main_module
from text.script_parser import parse as parse_script


def test_run_prints_board_on_print_command(capsys):
    lines = ["Board:", "wK . bK", "Commands:", "print"]
    main_module.run(lines)
    out = capsys.readouterr().out
    assert out.strip() == "wK . bK"


def test_run_reports_parse_error(capsys):
    lines = ["Board:", "wX . bK", "Commands:", "print"]
    main_module.run(lines)
    out = capsys.readouterr().out
    assert out.startswith("ERROR")


def test_dispatch_ignores_blank_command():
    assert parse_script([""]) == []


def test_run_canonical_output_normalizes_whitespace(capsys):
    lines = ["Board:", "wK    .\tbK", "Commands:", "print"]
    main_module.run(lines)
    out = capsys.readouterr().out
    assert out.strip() == "wK . bK"


def test_run_prints_multi_row_board(capsys):
    lines = ["Board:", "wK . bK", ". . .", "Commands:", "print"]
    main_module.run(lines)
    out = capsys.readouterr().out
    assert out.strip("\n") == "wK . bK\n. . ."


def test_run_prints_empty_string_for_empty_board(capsys):
    lines = ["Board:", "Commands:", "print"]
    main_module.run(lines)
    out = capsys.readouterr().out
    assert out == "\n"


def test_run_no_output_without_print_command(capsys):
    lines = ["Board:", "wK . bK", "Commands:"]
    main_module.run(lines)
    out = capsys.readouterr().out
    assert out == ""


def test_run_click_wait_print_board_moves_piece(capsys):
    lines = [
        "Board:",
        "wR . .",
        ". . .",
        ". . .",
        "Commands:",
        "click 50 50",
        "click 250 50",
        "wait 2000",
        "print board",
    ]
    main_module.run(lines)
    out = capsys.readouterr().out
    assert out.strip("\n") == ". . wR\n. . .\n. . ."


def test_run_print_board_before_move_settles_shows_original_position(capsys):
    lines = [
        "Board:",
        "wR . .",
        ". . .",
        ". . .",
        "Commands:",
        "click 50 50",
        "click 250 50",
        "print board",
    ]
    main_module.run(lines)
    out = capsys.readouterr().out
    assert out.strip("\n") == "wR . .\n. . .\n. . ."


def test_run_ignores_move_commands_after_game_over(capsys):
    lines = [
        "Board:",
        "wR . bK",
        ". . .",
        "wN . .",
        "Commands:",
        "click 50 50",
        "click 250 50",
        "wait 2000",
        "print board",
        "click 50 250",
        "click 150 250",
        "wait 2000",
        "print board",
    ]
    main_module.run(lines)
    rows = capsys.readouterr().out.strip("\n").split("\n")
    assert "\n".join(rows[:3]) == "\n".join(rows[3:])


def test_run_move_appears_only_after_enough_accumulated_wait(capsys):
    lines = [
        "Board:",
        "wR . .",
        ". . .",
        ". . .",
        "Commands:",
        "click 50 50",
        "click 250 50",
        "wait 1000",
        "print board",
        "wait 1000",
        "print board",
    ]
    main_module.run(lines)
    rows = capsys.readouterr().out.strip("\n").split("\n")
    assert "\n".join(rows[:3]) == "wR . .\n. . .\n. . ."
    assert "\n".join(rows[3:]) == ". . wR\n. . .\n. . ."
