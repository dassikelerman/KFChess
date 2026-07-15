"""Translates a PieceSnapshot's logical fields into an AnimationState -
GameEngine only ever reports logical facts (is_moving/is_jumping), never
an AnimationState itself; deriving one from those facts is exclusively
the view's job.
"""

from model.piece import AnimationState


def derive_animation_state(piece_snapshot):
    if piece_snapshot.is_moving:
        return AnimationState.MOVE
    if piece_snapshot.is_jumping:
        return AnimationState.JUMP
    return AnimationState.IDLE
