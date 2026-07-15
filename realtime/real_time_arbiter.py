from dataclasses import replace

from model.game_state import ArrivalEvent
from model.piece import PieceKind
from realtime.motion import Jump, Motion


class RealTimeArbiter:
    """Owns real-time state: in-flight motions, active jumps, and the
    clock driving them.

    A jump intercepting a move is a single, tightly coupled mechanism, so
    both continue to live together here rather than being split across
    files. This is a mechanical service: it mutates the board it's given
    and reports what arrived via ArrivalEvents, but never decides what an
    arrival *means* (game over, promotion) - that's left to the caller.

    A piece leaves the Board the instant its Motion starts (see
    start_motion) and travels only as data on that Motion until it lands
    - nothing on the Board itself is "moving". advance_time() resolves,
    in strict chronological order, both final arrivals and in-transit
    collisions between motions whose paths cross (see Motion.path_cells).
    """

    def __init__(self, board):
        self._board = board
        self._clock = 0
        self._active_motions = []
        self._active_jumps = []
        self._cooldowns = {}  # piece_id -> (start_time, end_time) of its current rest

    @property
    def clock(self):
        return self._clock

    def is_resting(self, piece_id):
        """Whether this piece is currently in a post-move/post-jump
        cooldown (see GameEngine's long/short rest handling) and can't
        act again yet. Purely a time comparison - callers set the
        cooldown itself via set_cooldown()."""
        return self.rest_remaining_fraction(piece_id) is not None

    def set_cooldown(self, piece_id, duration_ms):
        self._cooldowns[piece_id] = (self._clock, self._clock + duration_ms)

    def rest_remaining_fraction(self, piece_id):
        """How much of this piece's current rest is still left, as a
        fraction from 1.0 (just started resting) down to just above 0.0
        (about to finish) - or None if it isn't resting at all. Purely
        for rendering a fading cooldown indicator; game rules only ever
        need the boolean is_resting()."""
        entry = self._cooldowns.get(piece_id)
        if entry is None:
            return None
        start_time, end_time = entry
        if self._clock >= end_time:
            return None
        total = end_time - start_time
        if total <= 0:
            return 0.0
        return (end_time - self._clock) / total

    def active_jumps(self):
        """A read-only snapshot of every currently active jump - lets a
        caller (GameEngine) see which ones are about to expire in an
        upcoming advance_time() call, before that call silently drops
        them from _active_jumps."""
        return list(self._active_jumps)

    def has_active_motion(self, cell=None):
        if cell is None:
            return bool(self._active_motions)
        return self.active_motion_from(cell) is not None

    def active_motion_from(self, cell):
        """The Motion currently departing FROM this cell (cell ==
        motion.source), or None.

        A piece leaves its source the instant its motion starts and is
        never "back" there until it actually lands elsewhere, so this is
        purely a lookup over active motions - no board state is involved.
        It's possible (if unusual) for more than one active motion to
        share a source: a piece can legally move into a cell another
        piece just vacated, and then itself depart again before the
        original motion has resolved. The most recently started motion
        is what's actually relevant to that cell right now, so ties are
        broken in its favour.
        """
        candidates = [m for m in self._active_motions if m.source == cell]
        if not candidates:
            return None
        return max(candidates, key=lambda m: m.start_time)

    def is_jumping_on(self, cell):
        return any(jump.cell == cell for jump in self._active_jumps)

    def active_motion_for(self, piece_id):
        """The Motion currently in flight for this piece, or None -
        read-only lookup by identity (never by cell; see has_active_motion)
        for callers like GameEngine.snapshot() that need to render a
        specific piece's progress without reaching into _active_motions."""
        return next((m for m in self._active_motions if m.piece_id == piece_id), None)

    def active_motions(self):
        """A read-only snapshot of every currently in-flight motion - a
        piece leaves the Board entirely the instant its motion starts
        (see start_motion), so callers like GameEngine.snapshot() need
        this to know which pieces exist at all right now beyond what
        board.pieces() alone would show."""
        return list(self._active_motions)

    def active_jump_for(self, cell):
        """The Jump currently guarding this cell, or None - Jump is
        deliberately cell-based rather than tied to a piece's identity
        (see is_jumping_on), so this is keyed by cell too."""
        return next((j for j in self._active_jumps if j.cell == cell), None)

    def start_motion(self, piece, source, destination, duration_ms):
        start_time = self._clock
        arrival_time = self._clock + duration_ms
        self._active_motions.append(Motion(piece, source, destination, start_time, arrival_time))
        # The piece leaves its source cell the instant the motion is
        # queued - it travels as data on the Motion, not as a Board
        # occupant, so nothing can capture or block it at its old cell
        # while it's airborne (see Motion's own docstring).
        self._board.remove_piece(piece)

    def start_jump(self, cell, end_time):
        self._active_jumps.append(Jump(cell, end_time))

    def advance_time(self, ms):
        if ms < 0:
            raise ValueError(f"advance_time expects a non-negative duration, got {ms}")

        new_clock = self._clock + ms
        events = []

        # Resolve every arrival and in-transit collision due by new_clock,
        # strictly in chronological order - never by insertion order or
        # frame-to-frame call granularity - so the outcome is identical
        # whether this is one big advance_time() call or several small
        # ones covering the same total span. Each processed event can
        # change what's still active (an arrival removes a motion; a
        # collision removes or truncates one), so the next event is
        # recomputed from scratch every iteration rather than planned
        # upfront.
        while True:
            outcome = self._next_event(new_clock)
            if outcome is None:
                break
            if outcome[0] == "arrival":
                event = self._resolve_arrival(outcome[1])
                if event is not None:
                    events.append(event)
            else:
                _, motion_a, motion_b, cell = outcome
                events.extend(self._resolve_collision(motion_a, motion_b, cell))

        self._clock = new_clock
        self._active_jumps = [j for j in self._active_jumps if self._clock < j.end_time]
        return events

    def _next_event(self, new_clock):
        candidates = []
        for motion in self._active_motions:
            if motion.arrival_time <= new_clock:
                candidates.append((motion.arrival_time, 1, (motion.piece_id,), ("arrival", motion)))

        for i, motion_a in enumerate(self._active_motions):
            for motion_b in self._active_motions[i + 1:]:
                collision = self._collision_between(motion_a, motion_b)
                if collision is None:
                    continue
                time, cell = collision
                if time <= new_clock:
                    tie_key = tuple(sorted((motion_a.piece_id, motion_b.piece_id)))
                    candidates.append((time, 0, tie_key, ("collision", motion_a, motion_b, cell)))

        if not candidates:
            return None
        candidates.sort(key=lambda c: c[:3])
        return candidates[0][3]

    def _collision_between(self, motion_a, motion_b):
        shared = set(motion_a.path_cells()) & set(motion_b.path_cells())
        if not shared:
            return None
        best = None
        for cell in shared:
            time = max(motion_a.time_at_cell(cell), motion_b.time_at_cell(cell))
            key = (time, cell.row, cell.col)
            if best is None or key < best[0]:
                best = (key, cell)
        (time, _, _), cell = best
        return time, cell

    def _resolve_collision(self, motion_a, motion_b, cell):
        # One (or both) side of this pairing may have already been
        # resolved or truncated by an earlier event processed in this
        # same advance_time() call (e.g. one of them already collided
        # with a third motion first) - if so, this candidate is stale
        # and simply dropped; _next_event() recomputes fresh each time.
        if motion_a not in self._active_motions or motion_b not in self._active_motions:
            return []

        time_a = motion_a.time_at_cell(cell)
        time_b = motion_b.time_at_cell(cell)
        same_color = motion_a.piece.color == motion_b.piece.color

        if time_a == time_b:
            if same_color:
                motion_a.truncate_before(cell)
                motion_b.truncate_before(cell)
                return []
            # Exact simultaneous meeting between enemies: there's no
            # well-defined "who got there first" to decide a winner, so
            # neither survives - a documented, deterministic policy (see
            # tests) rather than an arbitrary tie-break.
            self._active_motions.remove(motion_a)
            self._active_motions.remove(motion_b)
            return [self._self_destroyed_event(motion_a, cell), self._self_destroyed_event(motion_b, cell)]

        early, late = (motion_a, motion_b) if time_a < time_b else (motion_b, motion_a)
        if same_color:
            # The earlier motion already claimed this cell and continues
            # untouched; the later one can't pass through/land on a
            # friendly claim, so it stops one cell short instead.
            late.truncate_before(cell)
            return []

        # Different colors: whichever motion reaches the shared cell
        # later captures the one that was already there, and continues
        # on to its own original destination.
        self._active_motions.remove(early)
        return [ArrivalEvent(
            piece_id=late.piece.id,
            source=late.source,
            destination=cell,
            captured_piece_id=early.piece.id,
            king_captured=early.piece.kind == PieceKind.KING,
        )]

    def _self_destroyed_event(self, motion, cell):
        return ArrivalEvent(
            piece_id=motion.piece.id,
            source=motion.source,
            destination=cell,
            captured_piece_id=motion.piece.id,
            king_captured=motion.piece.kind == PieceKind.KING,
        )

    def _resolve_arrival(self, motion):
        self._active_motions.remove(motion)
        piece = motion.piece

        if self._is_intercepted(motion, piece):
            return ArrivalEvent(
                piece_id=piece.id,
                source=motion.source,
                destination=motion.destination,
                captured_piece_id=piece.id,
                king_captured=piece.kind == PieceKind.KING,
            )

        target = self._board.piece_at(motion.destination)
        if target is not None and target.color == piece.color:
            # A stationary friendly piece here would already have failed
            # RuleEngine validation before this motion was ever queued -
            # so this can only be another (now-resolved) motion that beat
            # this one to their shared destination with a *different*
            # arrival time (an exact tie is caught earlier, in
            # _resolve_collision, before either side gets here). This is
            # the same "can't land on a friendly claim" situation as an
            # in-transit collision, just realized one step later than
            # usual: stop one cell short and let the next loop iteration
            # resolve the (now shorter, already-due) motion for real.
            if motion.destination == motion.source:
                return None  # nowhere shorter to go - it never arrives
            motion.truncate_before(motion.destination)
            self._active_motions.append(motion)
            return None

        captured_piece_id = None if target is None else target.id
        king_captured = target is not None and target.kind == PieceKind.KING

        self._board.add_piece(replace(piece, cell=motion.destination))

        return ArrivalEvent(
            piece_id=piece.id,
            source=motion.source,
            destination=motion.destination,
            captured_piece_id=captured_piece_id,
            king_captured=king_captured,
        )

    def _is_intercepted(self, motion, piece):
        # A jump only intercepts if the cell it guards is still actually
        # defended by *some* piece - an empty guarded cell (e.g. left
        # behind if its defender is ever removed some other way) must not
        # intercept everything indiscriminately, which unguarded None !=
        # piece.color would otherwise do.
        return any(
            jump.cell == motion.destination and self._piece_color(jump.cell) not in (None, piece.color)
            for jump in self._active_jumps
        )

    def _piece_color(self, cell):
        piece = self._board.piece_at(cell)
        return piece.color if piece is not None else None
