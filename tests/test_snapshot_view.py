from client.snapshot_view import SnapshotView
from engine.game_conditions import KingCaptureWinCondition, LastRankPromotion
from engine.game_engine import GameEngine
from engine.snapshot import GameSnapshot, PieceSnapshot
from model.board import Board
from model.piece import PieceColor, PieceKind
from model.position import Position
from realtime.real_time_arbiter import RealTimeArbiter
from rules.rule_engine import RuleEngine, build_default_registry


def make_piece(id_, row, col, is_jumping=False, is_moving=False, rest_fraction_remaining=None):
    return PieceSnapshot(
        id=id_, kind=PieceKind.ROOK, color=PieceColor.WHITE,
        row=row, col=col, render_row=float(row), render_col=float(col),
        is_moving=is_moving, is_jumping=is_jumping, rest_fraction_remaining=rest_fraction_remaining,
    )


def make_snapshot(pieces, game_over=False):
    return GameSnapshot(board_width=3, board_height=3, pieces=pieces, game_over=game_over)


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
    return engine


def test_update_stores_the_snapshot_and_clock():
    view = SnapshotView()
    snapshot = make_snapshot([])

    view.update(snapshot, 1500)

    assert view.snapshot() is snapshot
    assert view.clock == 1500


def test_snapshot_and_clock_are_empty_before_the_first_update():
    view = SnapshotView()
    assert view.snapshot() is None
    assert view.clock == 0


def test_game_over_is_false_before_the_first_update():
    view = SnapshotView()
    assert view.game_over is False


def test_game_over_reflects_the_stored_snapshot():
    view = SnapshotView()
    view.update(make_snapshot([], game_over=True), 0)
    assert view.game_over is True

    view.update(make_snapshot([], game_over=False), 0)
    assert view.game_over is False


def test_piece_at_finds_the_piece_occupying_a_cell():
    piece = make_piece("p1", row=1, col=2)
    view = SnapshotView()
    view.update(make_snapshot([piece]), 0)

    assert view.piece_at(Position(1, 2)) is piece


def test_piece_at_returns_none_for_an_empty_cell():
    view = SnapshotView()
    view.update(make_snapshot([make_piece("p1", row=1, col=2)]), 0)

    assert view.piece_at(Position(0, 0)) is None


def test_piece_at_returns_none_before_any_update():
    view = SnapshotView()
    assert view.piece_at(Position(0, 0)) is None


def test_is_busy_is_true_only_for_a_piece_flagged_as_jumping_at_that_cell():
    view = SnapshotView()
    view.update(make_snapshot([make_piece("p1", row=0, col=0, is_jumping=True)]), 0)

    assert view.is_busy(Position(0, 0)) is True
    assert view.is_busy(Position(1, 1)) is False


def test_is_busy_is_false_for_a_piece_present_but_not_jumping():
    view = SnapshotView()
    view.update(make_snapshot([make_piece("p1", row=0, col=0, is_jumping=False)]), 0)

    assert view.is_busy(Position(0, 0)) is False


def test_is_busy_matches_the_real_arbiters_is_jumping_on_semantics_mid_jump():
    engine = make_engine([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    engine.request_jump(Position(0, 0))

    view = SnapshotView()
    view.update(engine.snapshot(), engine.clock)

    checked_any_busy = False
    for row in range(3):
        for col in range(3):
            pos = Position(row, col)
            assert view.is_busy(pos) == engine.is_busy(pos), pos
            checked_any_busy = checked_any_busy or engine.is_busy(pos)

    # Sanity check the comparison loop actually exercised a busy cell -
    # otherwise every assertion above would trivially pass on all-False.
    assert checked_any_busy is True
