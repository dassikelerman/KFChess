"""Layers the one-shot rest states (LONG_REST/SHORT_REST) on top of the
IDLE/MOVE/JUMP derived from GameEngine's logical PieceSnapshot fields.
Driven by AnimationLibrary's own next_state_when_finished, so the
transition table isn't hardcoded here - see docs for the full chain.

Also the single source of truth for how long a piece has been in its
current AnimationState - a renderer needs that elapsed time to pick the
right frame (see view.piece_animations.frame_index_for), and tracking
it here rather than in a second, parallel timer keeps the "when did
this piece's state last change" bookkeeping in one place.
"""

from dataclasses import dataclass

from view.animation_state import AnimationState, derive_animation_state

_STATE_BY_VALUE = {state.value: state for state in AnimationState}


@dataclass(frozen=True)
class AnimationProgress:
    state: AnimationState
    elapsed_ms: float


class PieceStateMachine:
    def __init__(self, animation_library):
        self._library = animation_library
        self._entries = {}  # piece_id -> (AnimationState, entered_at_ms)

    def state_for(self, piece_snapshot, clock_ms):
        engine_state = derive_animation_state(piece_snapshot)

        if engine_state in (AnimationState.MOVE, AnimationState.JUMP):
            return self._enter(piece_snapshot.id, engine_state, clock_ms)

        entry = self._entries.get(piece_snapshot.id)
        if entry is None:
            return self._enter(piece_snapshot.id, AnimationState.IDLE, clock_ms)

        state, entered_at = entry
        if state == AnimationState.IDLE:
            return AnimationProgress(AnimationState.IDLE, clock_ms - entered_at)

        if state in (AnimationState.MOVE, AnimationState.JUMP):
            # Engine just reported idle right after move/jump - hand off
            # to whatever that clip's own config says comes next.
            next_state = self._next_state(piece_snapshot, state)
            return self._enter(piece_snapshot.id, next_state, clock_ms)

        if self._clip_finished(piece_snapshot, state, clock_ms - entered_at):
            next_state = self._next_state(piece_snapshot, state)
            return self._enter(piece_snapshot.id, next_state, clock_ms)

        return AnimationProgress(state, clock_ms - entered_at)

    def forget(self, piece_id):
        self._entries.pop(piece_id, None)

    def _enter(self, piece_id, state, clock_ms):
        entry = self._entries.get(piece_id)
        if entry is None or entry[0] != state:
            self._entries[piece_id] = (state, clock_ms)
            return AnimationProgress(state, 0.0)
        _, entered_at = entry
        return AnimationProgress(state, clock_ms - entered_at)

    def _next_state(self, piece_snapshot, state):
        clip = self._library.get(piece_snapshot.color, piece_snapshot.kind, state)
        return _STATE_BY_VALUE[clip.config.next_state_when_finished]

    def _clip_finished(self, piece_snapshot, state, elapsed_ms):
        clip = self._library.get(piece_snapshot.color, piece_snapshot.kind, state)
        frame_count = len(clip.sprite_paths)
        one_cycle_ms = (frame_count / clip.config.frames_per_sec) * 1000
        return elapsed_ms >= one_cycle_ms
