import types

import main as main_module


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


def test_run_accepts_injected_config(capsys):
    custom_config = types.SimpleNamespace(
        CELL_SIZE=50,
        MOVE_DURATION=10,
        JUMP_DURATION=10,
        COLORS=("w", "b"),
        PAWN_DIRECTION={"w": -1, "b": 1},
        PAWN_START_ROW={"w": 1, "b": 6},
        EMPTY_CELL=".",
    )
    lines = ["Board:", "wK . bK", "Commands:", "print"]
    main_module.run(lines, config=custom_config)
    out = capsys.readouterr().out
    assert out.strip() == "wK . bK"


def test_dispatch_ignores_blank_command():
    # Should not raise for an empty command line.
    main_module._dispatch("", engine=None, renderer=None)


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
