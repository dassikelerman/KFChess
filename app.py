"""KungFu Chess - entry point.

Repository: <insert-git-repository-url-here>
"""
import sys
from dataclasses import dataclass

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
    registry = build_default_registry(pawn_direction={"w": -1, "b": 1})
    board = build_board(board_text, registry, colors=("w", "b"), empty_cell=".")

    engine = GameEngine(
        board=board,
        rule_engine=RuleEngine(registry),
        arbiter=RealTimeArbiter(board),
        win_condition=KingCaptureWinCondition(),
        promotion_rule=LastRankPromotion(),
        move_duration=1000,
        jump_duration=1000,
    )
    board_mapper = BoardMapper(cell_size=100, board_width=board.width, board_height=board.height)
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

    printer = BoardPrinter()
    runner = ScriptRunner(app.controller, app.engine, printer)
    commands = parse_script(command_lines)
    runner.run(commands)


def main():
    lines = [line.strip() for line in sys.stdin]
    run(lines)


if __name__ == "__main__":
    main()
