"""KungFu Chess - entry point.

Repository: <insert-git-repository-url-here>
"""
import sys
from dataclasses import dataclass

import constants
from rules.rule_engine import RuleEngine, build_default_registry
from engine.game_conditions import KingCaptureWinCondition, LastRankPromotion
from realtime.real_time_arbiter import RealTimeArbiter
from input.board_mapper import BoardMapper
from input.controller import Controller
from board_io.board_parser import parse_input, build_board, BoardParseError
from board_io.board_printer import BoardPrinter
from engine.game_engine import GameEngine
from texttests.script_parser import parse as parse_script
from texttests.script_runner import ScriptRunner


@dataclass
class AppComponents:
    engine: GameEngine
    controller: Controller


def build_app(board_text):
    """Compose the full object graph for one game: Board, RuleEngine,
    RealTimeArbiter, GameEngine, BoardMapper, Controller. No line-parsing
    logic lives here - board_text is already the board section's lines;
    this function only builds and wires collaborators together, feeding
    each one the literal constants it needs directly.
    """
    registry = build_default_registry(pawn_direction=constants.PAWN_DIRECTION)
    board = build_board(board_text, colors=constants.COLORS, empty_cell=constants.EMPTY_CELL)

    engine = GameEngine(
        board=board,
        rule_engine=RuleEngine(registry),
        arbiter=RealTimeArbiter(board),
        win_condition=KingCaptureWinCondition(),
        promotion_rule=LastRankPromotion(),
        move_duration=constants.MOVE_DURATION,
        jump_duration=constants.JUMP_DURATION,
    )
    board_mapper = BoardMapper(
        cell_size=constants.CELL_SIZE, board_width=board.width, board_height=board.height
    )
    controller = Controller(engine, board_mapper)

    return AppComponents(engine=engine, controller=controller)


def run(input_lines):
    """Parse input and execute all commands."""
    board_lines, command_lines = parse_input(input_lines)

    try:
        app = build_app(board_lines)
    except BoardParseError as error:
        print("ERROR", error)
        return

    printer = BoardPrinter(empty_token=constants.EMPTY_CELL)
    runner = ScriptRunner(app.controller, app.engine, printer)
    commands = parse_script(command_lines)
    runner.run(commands)


def main():
    lines = [line.strip() for line in sys.stdin]
    run(lines)


if __name__ == "__main__":
    main()
