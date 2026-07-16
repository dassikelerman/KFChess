from model.board import Board
from model.piece import PieceColor, PieceKind
from model.position import Position
from rules.rule_engine import RuleEngine, build_default_registry
from engine.game_conditions import KingCaptureWinCondition, LastRankPromotion
from engine.game_engine import GameEngine
from realtime.real_time_arbiter import RealTimeArbiter

from events.dispatcher import EventDispatcher
from events.game_events import (
    CaptureEvent,
    GameOverEvent,
    JumpCompletedEvent,
    MotionStoppedEvent,
    MoveCompletedEvent,
    PromotionEvent,
)

MOVE_DURATION = 1000
JUMP_DURATION = 1000
LONG_REST_DURATION = 0
SHORT_REST_DURATION = 0


def make_engine(rows, promotion_rule=None, move_duration=MOVE_DURATION, long_rest_duration=LONG_REST_DURATION):
    board = Board(rows)
    registry = build_default_registry(pawn_direction={"w": -1, "b": 1})
    dispatcher = EventDispatcher()
    engine = GameEngine(
        board=board,
        rule_engine=RuleEngine(registry),
        arbiter=RealTimeArbiter(board),
        win_condition=KingCaptureWinCondition(),
        promotion_rule=promotion_rule or LastRankPromotion(),
        move_duration=move_duration,
        jump_duration=JUMP_DURATION,
        long_rest_duration=long_rest_duration,
        short_rest_duration=SHORT_REST_DURATION,
        dispatcher=dispatcher,
    )
    return engine, board, dispatcher


def collect(dispatcher, *event_types):
    collected = []
    for event_type in event_types:
        dispatcher.subscribe(event_type, collected.append)
    return collected


# -- Move completed -------------------------------------------------------


def test_move_completed_event_publishes_on_a_clean_landing():
    engine, board, dispatcher = make_engine([["wR", ".", "."]])
    events = collect(dispatcher, MoveCompletedEvent)

    engine.request_move(Position(0, 0), Position(0, 2))
    engine.wait(MOVE_DURATION * 2)

    assert len(events) == 1
    assert events[0].piece_kind == PieceKind.ROOK
    assert events[0].piece_color == PieceColor.WHITE
    assert events[0].destination == Position(0, 2)


# -- Capture ----------------------------------------------------------------


def test_capture_event_publishes_with_capturer_and_victim_kind_and_color():
    engine, board, dispatcher = make_engine([["wR", ".", "bP"]])
    events = collect(dispatcher, CaptureEvent)

    engine.request_move(Position(0, 0), Position(0, 2))
    engine.wait(MOVE_DURATION * 2)

    assert len(events) == 1
    event = events[0]
    assert event.piece_kind == PieceKind.ROOK
    assert event.piece_color == PieceColor.WHITE
    assert event.captured_kind == PieceKind.PAWN
    assert event.captured_color == PieceColor.BLACK
    assert event.at == Position(0, 2)


def test_capture_event_publishes_for_a_mid_path_encounter_even_though_the_attacker_has_not_landed():
    # Reproduces the mid-flight pass-through fix: a rook flies the length
    # of a column, a pawn steps into its path, and the capture is
    # reported before the rook's own (later) landing - proving the
    # Capture event doesn't wait for GameEngine to see the attacker land.
    rows = [["wR", "."], [".", "."], [".", "."], [".", "."], ["bR", "."]]
    engine, board, dispatcher = make_engine(rows, move_duration=100)
    events = collect(dispatcher, CaptureEvent, MoveCompletedEvent)

    engine.request_move(Position(0, 0), Position(4, 0))  # white rook: reaches (3,0) at t=300
    engine.wait(150)
    engine.request_move(Position(4, 0), Position(3, 0))  # black rook steps into the white rook's path
    engine.wait(400)

    # Three real, distinct occurrences: the black rook lands safely on
    # its own short hop first (t=250), then the white rook's flight path
    # catches up to that same cell (t=300) and captures it there, then
    # the white rook continues on to its own destination (t=400).
    assert len(events) == 3
    black_landing, capture, white_landing = events
    assert isinstance(black_landing, MoveCompletedEvent)
    assert black_landing.destination == Position(3, 0)
    assert isinstance(capture, CaptureEvent)
    assert capture.captured_kind == PieceKind.ROOK
    assert capture.captured_color == PieceColor.BLACK
    assert capture.at == Position(3, 0)
    assert isinstance(white_landing, MoveCompletedEvent)
    assert white_landing.destination == Position(4, 0)


# -- Jump completed -----------------------------------------------------


def test_jump_completed_event_publishes_when_the_jump_window_ends():
    engine, board, dispatcher = make_engine([["bP", "."]])
    events = collect(dispatcher, JumpCompletedEvent)

    engine.request_jump(Position(0, 0))
    engine.wait(JUMP_DURATION)

    assert len(events) == 1
    assert events[0].piece_kind == PieceKind.PAWN
    assert events[0].piece_color == PieceColor.BLACK
    assert events[0].cell == Position(0, 0)


# -- Motion stopped -------------------------------------------------------


def test_motion_stopped_event_publishes_when_a_move_is_intercepted_by_a_jump_guard():
    rows = [["wR", "bP"], [".", "."]]
    engine, board, dispatcher = make_engine(rows)
    events = collect(dispatcher, MotionStoppedEvent, CaptureEvent, MoveCompletedEvent)

    engine.request_jump(Position(0, 1))
    engine.request_move(Position(0, 0), Position(0, 1))
    engine.wait(JUMP_DURATION)

    stopped = [e for e in events if isinstance(e, MotionStoppedEvent)]
    assert len(stopped) == 1
    assert stopped[0].piece_kind == PieceKind.ROOK
    assert stopped[0].piece_color == PieceColor.WHITE
    # An intercepted piece never lands, so it is never reported as a
    # capture or a completed move either.
    assert not [e for e in events if isinstance(e, (CaptureEvent, MoveCompletedEvent))]


# -- Promotion ------------------------------------------------------------


def test_promotion_event_does_not_publish_for_a_move_that_does_not_reach_the_last_rank():
    rows = [[".", "."], [".", "."], ["wP", "."], [".", "."]]
    engine, board, dispatcher = make_engine(rows)
    events = collect(dispatcher, PromotionEvent)

    engine.request_move(Position(2, 0), Position(1, 0))  # one step, not the last rank yet
    engine.wait(MOVE_DURATION)

    assert events == []


def test_promotion_event_publishes_when_a_pawn_lands_on_its_true_last_rank():
    rows = [
        [".", "."],
        [".", "."],
        ["wP", "."],
    ]
    engine, board, dispatcher = make_engine(rows)
    events = collect(dispatcher, PromotionEvent)

    engine.request_move(Position(2, 0), Position(1, 0))  # single step, not from its own start row
    engine.wait(MOVE_DURATION)
    engine.request_move(Position(1, 0), Position(0, 0))  # single step onto the last rank
    engine.wait(MOVE_DURATION)

    assert len(events) == 1
    assert events[0].piece_color == PieceColor.WHITE
    assert events[0].from_kind == PieceKind.PAWN
    assert events[0].to_kind == PieceKind.QUEEN
    assert events[0].at == Position(0, 0)


# -- Game over --------------------------------------------------------------


def test_game_over_event_publishes_with_the_winner_color():
    rows = [["wR", ".", "bK"]]
    engine, board, dispatcher = make_engine(rows)
    events = collect(dispatcher, GameOverEvent)

    engine.request_move(Position(0, 0), Position(0, 2))
    engine.wait(MOVE_DURATION * 2)

    assert len(events) == 1
    assert events[0].winner_color == PieceColor.WHITE


def test_capture_event_also_publishes_for_the_arrival_that_ends_the_game():
    rows = [["wR", ".", "bK"]]
    engine, board, dispatcher = make_engine(rows)
    events = collect(dispatcher, CaptureEvent, GameOverEvent)

    engine.request_move(Position(0, 0), Position(0, 2))
    engine.wait(MOVE_DURATION * 2)

    assert [type(e) for e in events] == [CaptureEvent, GameOverEvent]
    assert events[0].captured_kind == PieceKind.KING


# -- Ordering / stopping after game over -----------------------------------


def test_events_publish_in_the_same_chronological_order_arrivals_actually_land():
    rows = [["wR", ".", ".", "."], ["wR", ".", ".", "."]]
    engine, board, dispatcher = make_engine(rows)
    events = collect(dispatcher, MoveCompletedEvent)

    engine.request_move(Position(0, 0), Position(0, 3))  # distance 3 -> lands at t=3000
    engine.request_move(Position(1, 0), Position(1, 1))  # distance 1 -> lands at t=1000, first

    engine.wait(MOVE_DURATION * 3)

    assert [e.destination for e in events] == [Position(1, 1), Position(0, 3)]


def test_no_further_events_publish_for_later_same_batch_arrivals_after_game_over():
    # A rook flies the length of a column toward the enemy king's cell;
    # the king steps one cell out of the way, into a cell the rook's
    # path already covers, so the rook captures it in passing. A
    # separately-moving knight lands later in the very same wait() call.
    # The knight's own MoveCompletedEvent must never publish, even though
    # the arbiter mechanically finished resolving it.
    rows = [
        ["wR", "wN", "."],
        [".", ".", "."],
        [".", ".", "."],
        [".", ".", "."],
        ["bK", ".", "."],
    ]
    engine, board, dispatcher = make_engine(rows, move_duration=100, long_rest_duration=1000)
    events = collect(
        dispatcher, CaptureEvent, GameOverEvent, MoveCompletedEvent, MotionStoppedEvent,
    )

    engine.request_move(Position(0, 0), Position(4, 0))  # rook: reaches (3,0) at t=300
    engine.request_move(Position(4, 0), Position(3, 0))  # king sidesteps into the rook's path, lands t=100

    engine.wait(150)
    engine.request_move(Position(0, 1), Position(2, 2))  # knight lands at t=350, after the capture at t=300

    engine.wait(400)  # covers both t=300 (king captured) and t=350 (knight lands)

    assert engine.game_over is True
    # The king's own sidestep lands safely first (t=100) and is reported
    # normally; only then does the rook's flight path catch up to that
    # same cell (t=300) and capture it there.
    assert [type(e) for e in events] == [MoveCompletedEvent, CaptureEvent, GameOverEvent]
    # The knight really did land on the board later in the very same
    # batch (arbiter finished mechanically resolving everything up to the
    # new clock) - but GameEngine must never have published anything for
    # it, since game_over was already set by the time it was reached.
    assert events[0].piece_kind == PieceKind.KING
    assert sum(1 for e in events if isinstance(e, MoveCompletedEvent)) == 1


def test_no_event_publishes_for_a_piece_that_was_still_in_flight_when_the_game_ended():
    # A piece can still be mid-flight (queued before the fatal capture)
    # when the game ends - RealTimeArbiter has no concept of game_over
    # and will keep mechanically resolving it in a later wait() call
    # (exactly as view/run.py's loop keeps calling engine.wait() every
    # frame even after game_over is set). GameEngine must not publish an
    # event for that leftover resolution.
    rows = [
        ["wR", ".", "bK", ".", ".", "."],
        [".", ".", ".", ".", ".", "."],
        ["wR", ".", ".", ".", ".", "."],
    ]
    engine, board, dispatcher = make_engine(rows, move_duration=100)
    events = collect(dispatcher, CaptureEvent, GameOverEvent, MoveCompletedEvent)

    engine.request_move(Position(0, 0), Position(0, 2))  # captures the king at t=200
    engine.request_move(Position(2, 0), Position(2, 5))  # slow rook: needs 500ms, still flying at t=200

    engine.wait(200)
    assert engine.game_over is True
    assert [type(e) for e in events] == [CaptureEvent, GameOverEvent]

    engine.wait(400)  # pushes the clock past the slow rook's own t=500 landing

    assert board.piece_at(Position(2, 5)) is not None  # it really did land
    assert [type(e) for e in events] == [CaptureEvent, GameOverEvent]  # nothing new published


def test_no_events_publish_at_all_once_the_game_has_already_ended():
    rows = [["wR", ".", "bK"], [".", ".", "."], ["wN", ".", "."]]
    engine, board, dispatcher = make_engine(rows)

    engine.request_move(Position(0, 0), Position(0, 2))
    engine.wait(MOVE_DURATION * 2)
    assert engine.game_over is True

    events = collect(dispatcher, MoveCompletedEvent, CaptureEvent)
    # Nothing can legitimately be queued after game_over (request_move
    # rejects it), but even a lingering wait() call must not publish.
    engine.wait(MOVE_DURATION)

    assert events == []
