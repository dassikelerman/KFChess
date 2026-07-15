"""AnimationState and the logic to derive it - a view-side concept.
GameEngine only ever reports logical facts (is_moving/is_jumping), never
an AnimationState itself; deriving one from those facts is exclusively
the view's job.
"""

from enum import Enum


class AnimationState(Enum):
    """What a renderer should currently be playing for a piece - values
    match the asset folder names (pieces1/<TOKEN>/states/) exactly.

    LONG_REST/SHORT_REST are layered on top of derive_animation_state's
    IDLE/MOVE/JUMP by view.piece_state_machine.PieceStateMachine, without
    the engine needing to track "how long ago" anything happened.
    """

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
