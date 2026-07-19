from dataclasses import dataclass

import constants
from board_io.board_parser import build_board
from engine.game_conditions import KingCaptureWinCondition, LastRankPromotion
from engine.game_engine import GameEngine
from events.action_history import ActionHistory
from events.dispatcher import EventDispatcher
from events.score_tracker import ScoreTracker
from realtime.real_time_arbiter import RealTimeArbiter
from rules.rule_engine import RuleEngine, build_default_registry


@dataclass
class GameComponents:
    engine: GameEngine
    board: object  # model.board.Board
    dispatcher: EventDispatcher
    score_tracker: ScoreTracker
    action_history: ActionHistory


def build_game(board_text):
    registry = build_default_registry(pawn_direction=constants.PAWN_DIRECTION)
    board = build_board(board_text, colors=constants.COLORS, empty_cell=constants.EMPTY_CELL)

    dispatcher = EventDispatcher()
    score_tracker = ScoreTracker(dispatcher)
    action_history = ActionHistory(dispatcher)

    engine = GameEngine(
        board=board,
        rule_engine=RuleEngine(registry),
        arbiter=RealTimeArbiter(board),
        win_condition=KingCaptureWinCondition(),
        promotion_rule=LastRankPromotion(),
        move_duration=constants.MOVE_DURATION,
        jump_duration=constants.JUMP_DURATION,
        long_rest_duration=constants.LONG_REST_DURATION,
        short_rest_duration=constants.SHORT_REST_DURATION,
        dispatcher=dispatcher,
    )
    return GameComponents(
        engine=engine, board=board,
        dispatcher=dispatcher, score_tracker=score_tracker, action_history=action_history,
    )
