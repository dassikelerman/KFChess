from model.board import Board
from model.position import Position
from engine.game_conditions import KingCaptureWinCondition, LastRankPromotion
from engine.game_engine import GameEngine
from input.controller import Controller
from input.controller_builder import build_controller
from realtime.real_time_arbiter import RealTimeArbiter
from rules.rule_engine import RuleEngine, build_default_registry

CELL_SIZE = 100


def make_engine(rows):
    board = Board(rows)
    registry = build_default_registry(pawn_direction={"w": -1, "b": 1})
    engine = GameEngine(
        board=board,
        rule_engine=RuleEngine(registry),
        arbiter=RealTimeArbiter(board),
        win_condition=KingCaptureWinCondition(),
        promotion_rule=LastRankPromotion(),
        move_duration=1000,
        jump_duration=1000,
        long_rest_duration=0,
        short_rest_duration=0,
    )
    return engine, board


def test_game_engine_satisfies_the_action_sink_and_state_reader_shapes():
    engine, board = make_engine([["wK", "."], [".", "."]])

    # ActionSink/GameStateReader (input/controller.py) aren't
    # @runtime_checkable, so isinstance() can't confirm this - duck-type
    # check instead, against exactly what Controller calls through each
    # collaborator. GameEngine satisfies both Protocols structurally,
    # with no inheritance from either.
    assert callable(engine.request_move)
    assert callable(engine.request_jump)
    assert callable(engine.piece_at)
    assert callable(engine.is_busy)
    assert isinstance(engine.game_over, bool)


def test_build_controller_returns_a_controller():
    engine, board = make_engine([["wK", "."], [".", "."]])

    controller = build_controller(engine, engine, board.width, board.height, cell_size=CELL_SIZE)

    assert isinstance(controller, Controller)


class _FakePiece:
    def __init__(self, piece_id):
        self.id = piece_id


class _FakeStateReader:
    """Stands in for client/game_window.py::SnapshotView - board_width and
    board_height are taken as plain ints rather than read off a Board, since
    the network client only has a GameSnapshot, not a real Board."""

    def __init__(self, piece_at_origin):
        self.game_over = False
        self._piece_at_origin = piece_at_origin

    def piece_at(self, pos):
        return self._piece_at_origin if pos == Position(0, 0) else None

    def is_busy(self, pos):
        return False


class _FakeActionSink:
    def __init__(self):
        self.moves = []

    def request_move(self, source, destination):
        self.moves.append((source, destination))

    def request_jump(self, position):
        pass


def test_build_controller_works_with_a_distinct_action_sink_and_state_reader():
    # Mirrors client/run.py: ws_client (ActionSink) and snapshot_view
    # (GameStateReader) are two different objects, unlike the local flows
    # where the same GameEngine plays both roles.
    action_sink = _FakeActionSink()
    state_reader = _FakeStateReader(piece_at_origin=_FakePiece("some-piece"))
    controller = build_controller(action_sink, state_reader, board_width=2, board_height=2, cell_size=CELL_SIZE)

    controller.click(0, 0)

    assert controller.selected == (0, 0)


def test_zero_offset_maps_clicks_directly_to_board_cells():
    engine, board = make_engine([["wK", "."], [".", "."]])
    controller = build_controller(engine, engine, board.width, board.height, cell_size=CELL_SIZE)

    controller.click(0, 0)

    assert controller.selected == (0, 0)


def test_x_offset_shifts_the_boards_click_mapping_right():
    engine, board = make_engine([["wK", "."], [".", "."]])
    controller = build_controller(
        engine, engine, board.width, board.height, cell_size=CELL_SIZE, x_offset=220,
    )

    # A raw click at the panel offset lands on the board's own local (0, 0).
    controller.click(220, 0)
    assert controller.selected == (0, 0)


def test_x_offset_click_inside_the_panel_selects_nothing():
    engine, board = make_engine([["wK", "."], [".", "."]])
    controller = build_controller(
        engine, engine, board.width, board.height, cell_size=CELL_SIZE, x_offset=220,
    )

    # A click before the offset falls inside the panel, not the board.
    controller.click(50, 0)

    assert controller.selected is None


def test_y_offset_shifts_the_boards_click_mapping_down():
    engine, board = make_engine([["wK", "."], [".", "."]])
    controller = build_controller(
        engine, engine, board.width, board.height, cell_size=CELL_SIZE, y_offset=50,
    )

    controller.click(0, 50)

    assert controller.selected == (0, 0)


def test_y_offset_click_above_the_board_selects_nothing():
    engine, board = make_engine([["wK", "."], [".", "."]])
    controller = build_controller(
        engine, engine, board.width, board.height, cell_size=CELL_SIZE, y_offset=50,
    )

    controller.click(0, 0)

    assert controller.selected is None
