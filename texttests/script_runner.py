from config import settings
from rules.rule_engine import build_default_registry, KingCaptureWinCondition, LastRankPromotion
from board_io.board_parser import build_board, BoardParseError
from texttests.script_parser import parse_input
from engine.game_engine import GameEngine
from board_io.board_printer import BoardRenderer
from input.controller import _dispatch


def run(input_lines, config=settings):
    """Parse input and execute all commands. `config` is injectable so
    tests (or custom variants) can supply alternate settings without
    monkeypatching the settings module.
    """
    board_lines, commands = parse_input(input_lines)
    registry = build_default_registry(config)

    try:
        board = build_board(board_lines, registry, config)
    except BoardParseError as error:
        print("ERROR", error)
        return

    engine = GameEngine(
        board=board,
        rule_registry=registry,
        win_condition=KingCaptureWinCondition(),
        promotion_rule=LastRankPromotion(),
        config=config,
    )
    renderer = BoardRenderer()

    for command in commands:
        _dispatch(command, engine, renderer)
