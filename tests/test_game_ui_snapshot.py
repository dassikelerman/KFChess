from model.board import Board
from model.piece import PieceColor
from model.position import Position
from rules.rule_engine import RuleEngine, build_default_registry
from engine.game_conditions import KingCaptureWinCondition, LastRankPromotion
from engine.game_engine import GameEngine
from realtime.real_time_arbiter import RealTimeArbiter
from input.board_mapper import BoardMapper
from input.controller import Controller

from events.dispatcher import EventDispatcher
from events.score_tracker import ScoreTracker
from events.action_history import ActionHistory
from view.game_ui_snapshot import build_ui_snapshot

CELL_SIZE = 100


def make():
    board = Board([["wR", ".", "bP"]])
    registry = build_default_registry(pawn_direction={"w": -1, "b": 1})
    dispatcher = EventDispatcher()
    score_tracker = ScoreTracker(dispatcher)
    action_history = ActionHistory(dispatcher)
    engine = GameEngine(
        board=board, rule_engine=RuleEngine(registry), arbiter=RealTimeArbiter(board),
        win_condition=KingCaptureWinCondition(), promotion_rule=LastRankPromotion(),
        move_duration=100, jump_duration=1000, long_rest_duration=0, short_rest_duration=0,
        dispatcher=dispatcher,
    )
    board_mapper = BoardMapper(CELL_SIZE, board.width, board.height)
    controller = Controller(action_sink=engine, state_reader=engine, board_mapper=board_mapper)
    return engine, controller, score_tracker, action_history


def test_build_ui_snapshot_aggregates_the_game_snapshot_clock_and_selection():
    engine, controller, score_tracker, action_history = make()
    controller.click(0, 0)  # selects the white rook at (0, 0)

    ui_snapshot = build_ui_snapshot(engine, controller, score_tracker, action_history)

    assert ui_snapshot.game.pieces  # the real GameSnapshot, unmodified
    assert ui_snapshot.clock_ms == engine.clock
    assert ui_snapshot.selected == (0, 0)


def test_build_ui_snapshot_reports_no_selection_when_nothing_is_selected():
    engine, controller, score_tracker, action_history = make()

    ui_snapshot = build_ui_snapshot(engine, controller, score_tracker, action_history)

    assert ui_snapshot.selected is None


def test_build_ui_snapshot_includes_a_live_score_snapshot():
    engine, controller, score_tracker, action_history = make()

    engine.request_move(Position(0, 0), Position(0, 2))  # rook captures the pawn
    engine.wait(200)

    ui_snapshot = build_ui_snapshot(engine, controller, score_tracker, action_history)

    assert ui_snapshot.score[PieceColor.WHITE] == 1  # pawn = 1 point
    assert ui_snapshot.score[PieceColor.BLACK] == 0


def test_build_ui_snapshot_includes_recent_actions_from_action_history():
    engine, controller, score_tracker, action_history = make()

    engine.request_move(Position(0, 0), Position(0, 2))
    engine.wait(200)

    ui_snapshot = build_ui_snapshot(engine, controller, score_tracker, action_history)

    assert len(ui_snapshot.recent_actions) == 1
    assert "wR" in ui_snapshot.recent_actions[0].text


def test_build_ui_snapshot_respects_an_explicit_recent_action_count():
    engine, controller, score_tracker, action_history = make()

    for _ in range(3):
        engine.wait(0)  # no-ops, just to prove the count param is honored below

    ui_snapshot = build_ui_snapshot(engine, controller, score_tracker, action_history, recent_action_count=0)

    assert ui_snapshot.recent_actions == []


def test_game_ui_snapshot_is_a_separate_object_from_the_engines_own_snapshot():
    # GameSnapshot itself must stay untouched by score/history - this is
    # a distinct aggregate object the view layer builds on top of it.
    engine, controller, score_tracker, action_history = make()

    ui_snapshot = build_ui_snapshot(engine, controller, score_tracker, action_history)
    plain_snapshot = engine.snapshot()

    assert not hasattr(plain_snapshot, "score")
    assert not hasattr(plain_snapshot, "recent_actions")
    assert ui_snapshot.game.pieces == plain_snapshot.pieces


class _FakeStateSource:
    """Stands in for client/game_window.py::SnapshotView - build_ui_snapshot
    must work off just snapshot()/clock, the same two operations GameEngine
    exposes, with nothing else GameEngine-specific."""

    def __init__(self, snapshot, clock_ms):
        self._snapshot = snapshot
        self.clock = clock_ms

    def snapshot(self):
        return self._snapshot


def test_build_ui_snapshot_works_with_a_non_engine_state_source():
    engine, controller, score_tracker, action_history = make()
    fake_source = _FakeStateSource(snapshot=engine.snapshot(), clock_ms=1234)

    ui_snapshot = build_ui_snapshot(fake_source, controller, score_tracker, action_history)

    assert ui_snapshot.game == fake_source.snapshot()
    assert ui_snapshot.clock_ms == 1234
