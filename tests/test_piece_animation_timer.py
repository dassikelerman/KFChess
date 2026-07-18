from view.animation_state import AnimationState
from view.piece_animation_timer import PieceAnimationTimer


def test_first_sighting_of_a_piece_has_zero_elapsed():
    animator = PieceAnimationTimer()
    assert animator.elapsed_ms_for("p1", AnimationState.IDLE, clock_ms=500) == 0.0


def test_elapsed_grows_while_the_state_stays_the_same():
    animator = PieceAnimationTimer()
    animator.elapsed_ms_for("p1", AnimationState.MOVE, clock_ms=1000)

    elapsed = animator.elapsed_ms_for("p1", AnimationState.MOVE, clock_ms=1300)

    assert elapsed == 300


def test_elapsed_resets_to_zero_when_the_state_changes():
    animator = PieceAnimationTimer()
    animator.elapsed_ms_for("p1", AnimationState.MOVE, clock_ms=1000)
    animator.elapsed_ms_for("p1", AnimationState.MOVE, clock_ms=1500)

    elapsed = animator.elapsed_ms_for("p1", AnimationState.IDLE, clock_ms=1600)

    assert elapsed == 0.0


def test_different_pieces_are_tracked_independently():
    animator = PieceAnimationTimer()
    animator.elapsed_ms_for("p1", AnimationState.MOVE, clock_ms=1000)
    animator.elapsed_ms_for("p2", AnimationState.JUMP, clock_ms=1000)

    assert animator.elapsed_ms_for("p1", AnimationState.MOVE, clock_ms=1200) == 200
    assert animator.elapsed_ms_for("p2", AnimationState.JUMP, clock_ms=1200) == 200


def test_forget_makes_the_next_sighting_look_brand_new():
    animator = PieceAnimationTimer()
    animator.elapsed_ms_for("p1", AnimationState.MOVE, clock_ms=1000)

    animator.forget("p1")

    assert animator.elapsed_ms_for("p1", AnimationState.MOVE, clock_ms=5000) == 0.0
