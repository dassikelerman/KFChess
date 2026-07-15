class PieceAnimator:
    """Tracks, per piece id, how long it's been playing its current
    animation_state - purely a view-side concern. GameEngine.snapshot()
    only reports *which* state a piece is in right now (see AnimationState
    in model/piece.py), not how long it's been there; a renderer needs the
    elapsed time to pick the right frame via assets.piece_animations.
    frame_index_for.

    No cv2/pygame dependency - just bookkeeping - so it's unit testable
    without a display.
    """

    def __init__(self):
        self._entered_at = {}  # piece_id -> (AnimationState, clock_ms when it started)

    def elapsed_ms_for(self, piece_snapshot, clock_ms):
        entry = self._entered_at.get(piece_snapshot.id)
        if entry is None or entry[0] != piece_snapshot.animation_state:
            self._entered_at[piece_snapshot.id] = (piece_snapshot.animation_state, clock_ms)
            return 0.0
        _, started_at = entry
        return clock_ms - started_at

    def forget(self, piece_id):
        self._entered_at.pop(piece_id, None)
