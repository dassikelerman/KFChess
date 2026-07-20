import sys

import constants
from app.game_builder import build_game
from board_io.board_parser import BoardParseError, parse_input
from board_io.board_printer import BoardPrinter
from input.controller_builder import build_controller
from text.script_parser import parse as parse_script
from text.script_runner import ScriptRunner


def run(input_lines):
    board_lines, command_lines = parse_input(input_lines)

    try:
        game = build_game(board_lines)
    except BoardParseError as error:
        print("ERROR", error)
        return

    controller = build_controller(
        game.engine, game.engine, game.board.width, game.board.height, cell_size=constants.CELL_SIZE,
    )
    printer = BoardPrinter(empty_token=constants.EMPTY_CELL)
    runner = ScriptRunner(controller, game.engine, printer)
    commands = parse_script(command_lines)
    runner.run(commands)


def main():
    lines = [line.strip() for line in sys.stdin]
    run(lines)


if __name__ == "__main__":
    main()
