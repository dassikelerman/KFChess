from enum import Enum


class AnimationState(Enum):
    """A view-only concept: GameEngine reports logical facts only
    (is_moving/is_jumping), never an AnimationState. Values match the
    asset folder names (pieces2/<TOKEN>/states/) exactly."""

    IDLE = "idle"
    MOVE = "move"
    JUMP = "jump"
    LONG_REST = "long_rest"
    SHORT_REST = "short_rest"


def derive_animation_state(piece_snapshot):
    if piece_snapshot.is_moving:
        return AnimationState.MOVE
    if piece_snapshot.is_jumping:
        return AnimationState.JUMP
    return AnimationState.IDLE
