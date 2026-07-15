import os
from types import SimpleNamespace

import pytest

import constants
from assets.piece_animations import AnimationLibrary
from model.piece import AnimationState, PieceColor, PieceKind
from view.piece_state_machine import PieceStateMachine

PIECES_DIR_EXISTS = os.path.isdir(constants.PIECES_DIR)
requires_pieces_dir = pytest.mark.skipif(
    not PIECES_DIR_EXISTS, reason=f"{constants.PIECES_DIR}/ asset tree not present in this checkout"
)


class _FakeConfig:
    def __init__(self, next_state, fps):
        self.next_state_when_finished = next_state
        self.frames_per_sec = fps


class _FakeClip:
    def __init__(self, next_state, frame_count, fps):
        self.config = _FakeConfig(next_state, fps)
        self.sprite_paths = [f"{i}.png" for i in range(frame_count)]


class _FakeLibrary:
    """Mirrors the real pieces2/ transition chain (verified against every
    token): move -> long_rest -> idle, jump -> short_rest -> idle,
    idle -> idle. 5 frames at 10fps = 500ms per one-shot cycle."""

    _CHAIN = {
        AnimationState.IDLE: "idle",
        AnimationState.MOVE: "long_rest",
        AnimationState.JUMP: "short_rest",
        AnimationState.LONG_REST: "idle",
        AnimationState.SHORT_REST: "idle",
    }

    def get(self, color, kind, state):
        return _FakeClip(self._CHAIN[state], frame_count=5, fps=10)


def piece(id_, state, color="w", kind="Q"):
    return SimpleNamespace(id=id_, animation_state=state, color=color, kind=kind)


def test_engine_reported_move_is_returned_as_is():
    machine = PieceStateMachine(_FakeLibrary())
    state = machine.state_for(piece("p1", AnimationState.MOVE), clock_ms=1000)
    assert state == AnimationState.MOVE


def test_engine_reported_jump_is_returned_as_is():
    machine = PieceStateMachine(_FakeLibrary())
    state = machine.state_for(piece("p1", AnimationState.JUMP), clock_ms=1000)
    assert state == AnimationState.JUMP


def test_fresh_idle_piece_is_just_idle_no_fake_rest():
    machine = PieceStateMachine(_FakeLibrary())
    state = machine.state_for(piece("p1", AnimationState.IDLE), clock_ms=0)
    assert state == AnimationState.IDLE


def test_move_finishing_transitions_to_long_rest_not_idle():
    machine = PieceStateMachine(_FakeLibrary())
    machine.state_for(piece("p1", AnimationState.MOVE), clock_ms=1000)

    # the engine now reports idle - the piece just landed
    state = machine.state_for(piece("p1", AnimationState.IDLE), clock_ms=1200)

    assert state == AnimationState.LONG_REST


def test_jump_finishing_transitions_to_short_rest_not_idle():
    machine = PieceStateMachine(_FakeLibrary())
    machine.state_for(piece("p1", AnimationState.JUMP), clock_ms=1000)

    state = machine.state_for(piece("p1", AnimationState.IDLE), clock_ms=1200)

    assert state == AnimationState.SHORT_REST


def test_long_rest_persists_until_its_own_cycle_finishes_then_falls_back_to_idle():
    machine = PieceStateMachine(_FakeLibrary())
    machine.state_for(piece("p1", AnimationState.MOVE), clock_ms=0)
    machine.state_for(piece("p1", AnimationState.IDLE), clock_ms=100)  # enters long_rest at t=100

    # still within the one-shot cycle (500ms)
    state = machine.state_for(piece("p1", AnimationState.IDLE), clock_ms=400)
    assert state == AnimationState.LONG_REST

    # cycle has now played through once
    state = machine.state_for(piece("p1", AnimationState.IDLE), clock_ms=650)
    assert state == AnimationState.IDLE


def test_short_rest_persists_until_its_own_cycle_finishes_then_falls_back_to_idle():
    machine = PieceStateMachine(_FakeLibrary())
    machine.state_for(piece("p1", AnimationState.JUMP), clock_ms=0)
    machine.state_for(piece("p1", AnimationState.IDLE), clock_ms=100)  # enters short_rest at t=100

    state = machine.state_for(piece("p1", AnimationState.IDLE), clock_ms=400)
    assert state == AnimationState.SHORT_REST

    state = machine.state_for(piece("p1", AnimationState.IDLE), clock_ms=650)
    assert state == AnimationState.IDLE


def test_moving_again_while_resting_immediately_overrides_the_rest():
    machine = PieceStateMachine(_FakeLibrary())
    machine.state_for(piece("p1", AnimationState.MOVE), clock_ms=0)
    machine.state_for(piece("p1", AnimationState.IDLE), clock_ms=100)  # now resting (long_rest)

    # a brand new move starts before the rest cycle finishes
    state = machine.state_for(piece("p1", AnimationState.MOVE), clock_ms=200)

    assert state == AnimationState.MOVE


def test_different_pieces_are_tracked_independently():
    machine = PieceStateMachine(_FakeLibrary())
    machine.state_for(piece("p1", AnimationState.MOVE), clock_ms=0)
    machine.state_for(piece("p2", AnimationState.JUMP), clock_ms=0)

    state1 = machine.state_for(piece("p1", AnimationState.IDLE), clock_ms=50)
    state2 = machine.state_for(piece("p2", AnimationState.IDLE), clock_ms=50)

    assert state1 == AnimationState.LONG_REST
    assert state2 == AnimationState.SHORT_REST


def test_forget_makes_the_next_sighting_look_brand_new():
    machine = PieceStateMachine(_FakeLibrary())
    machine.state_for(piece("p1", AnimationState.MOVE), clock_ms=0)
    machine.state_for(piece("p1", AnimationState.IDLE), clock_ms=100)  # resting

    machine.forget("p1")

    state = machine.state_for(piece("p1", AnimationState.IDLE), clock_ms=150)
    assert state == AnimationState.IDLE  # no memory of having just moved


@requires_pieces_dir
def test_against_the_real_asset_library_move_transitions_through_long_rest_to_idle():
    library = AnimationLibrary(constants.PIECES_DIR)
    machine = PieceStateMachine(library)
    wq = piece("wq1", AnimationState.MOVE, color=PieceColor.WHITE, kind=PieceKind.QUEEN)

    machine.state_for(wq, clock_ms=0)
    state = machine.state_for(
        SimpleNamespace(id="wq1", animation_state=AnimationState.IDLE, color=PieceColor.WHITE, kind=PieceKind.QUEEN),
        clock_ms=10,
    )
    assert state == AnimationState.LONG_REST

    # QW/states/long_rest has 5 frames at 6fps -> one cycle is ~833ms
    idle_snapshot = SimpleNamespace(
        id="wq1", animation_state=AnimationState.IDLE, color=PieceColor.WHITE, kind=PieceKind.QUEEN
    )
    state = machine.state_for(idle_snapshot, clock_ms=2000)
    assert state == AnimationState.IDLE
