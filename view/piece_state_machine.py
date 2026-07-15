"""A view-side state machine over AnimationState (model/piece.py),
layering the one-shot rest states (LONG_REST/SHORT_REST) on top of what
GameEngine reports (IDLE/MOVE/JUMP) - see AnimationState's own docstring
for why the engine itself never produces LONG_REST/SHORT_REST: it's a
purely visual concern belonging to the view, not to game state.

Driven by the same AnimationLibrary (assets/piece_animations.py) already
used for rendering: each state's config.json carries its own
physics.next_state_when_finished, so the transition table isn't
hardcoded here - it's read from the same data the sprites/frames come
from (move -> long_rest -> idle, jump -> short_rest -> idle, idle ->
idle, for every piece in pieces2/).
"""

from model.piece import AnimationState

_STATE_BY_VALUE = {state.value: state for state in AnimationState}


class PieceStateMachine:
    """Tracks, per piece id, its *effective* AnimationState - which may
    be LONG_REST/SHORT_REST even though GameEngine.snapshot() only ever
    reports IDLE/MOVE/JUMP via PieceSnapshot.animation_state.

    No cv2/pygame dependency - just AnimationLibrary lookups and
    bookkeeping - so it's unit testable without a display.
    """

    def __init__(self, animation_library):
        self._library = animation_library
        self._entries = {}  # piece_id -> (AnimationState, entered_at_ms)

    def state_for(self, piece_snapshot, clock_ms):
        engine_state = piece_snapshot.animation_state

        if engine_state in (AnimationState.MOVE, AnimationState.JUMP):
            # The engine's own report is authoritative and immediate - a
            # piece can't be resting while it's actually moving/jumping.
            self._enter(piece_snapshot.id, engine_state, clock_ms)
            return engine_state

        entry = self._entries.get(piece_snapshot.id)
        if entry is None:
            self._enter(piece_snapshot.id, AnimationState.IDLE, clock_ms)
            return AnimationState.IDLE

        state, entered_at = entry
        if state == AnimationState.IDLE:
            return AnimationState.IDLE

        if state in (AnimationState.MOVE, AnimationState.JUMP):
            # The engine just reported idle right after move/jump - hand
            # off to whatever that clip's own config says comes next.
            state = self._next_state(piece_snapshot, state)
            self._enter(piece_snapshot.id, state, clock_ms)
            return state

        # Resting (long_rest/short_rest): stay until this clip has
        # played through once, then hand off the same way.
        if self._clip_finished(piece_snapshot, state, clock_ms - entered_at):
            state = self._next_state(piece_snapshot, state)
            self._enter(piece_snapshot.id, state, clock_ms)

        return state

    def forget(self, piece_id):
        self._entries.pop(piece_id, None)

    def _enter(self, piece_id, state, clock_ms):
        self._entries[piece_id] = (state, clock_ms)

    def _next_state(self, piece_snapshot, state):
        clip = self._library.get(piece_snapshot.color, piece_snapshot.kind, state)
        return _STATE_BY_VALUE[clip.config.next_state_when_finished]

    def _clip_finished(self, piece_snapshot, state, elapsed_ms):
        clip = self._library.get(piece_snapshot.color, piece_snapshot.kind, state)
        frame_count = len(clip.sprite_paths)
        one_cycle_ms = (frame_count / clip.config.frames_per_sec) * 1000
        return elapsed_ms >= one_cycle_ms
