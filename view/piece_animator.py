from view.animation_state import derive_animation_state


class PieceAnimator:
    """Tracks, per piece id, how long it's been playing its current
    AnimationState - a renderer needs the elapsed time to pick the right
    frame (see assets.piece_animations.frame_index_for)."""

    def __init__(self):
        self._entered_at = {}  # piece_id -> (AnimationState, clock_ms when it started)

    def elapsed_ms_for(self, piece_snapshot, clock_ms):
        state = derive_animation_state(piece_snapshot)
        entry = self._entered_at.get(piece_snapshot.id)
        if entry is None or entry[0] != state:
            self._entered_at[piece_snapshot.id] = (state, clock_ms)
            return 0.0
        _, started_at = entry
        return clock_ms - started_at

    def forget(self, piece_id):
        self._entered_at.pop(piece_id, None)
