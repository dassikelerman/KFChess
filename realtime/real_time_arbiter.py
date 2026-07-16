from dataclasses import replace

from model.game_state import ArrivalEvent, JumpEndedEvent
from model.piece import PieceKind
from realtime.motion import Jump, Motion


class RealTimeArbiter:
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
        return self.rest_remaining_fraction(piece_id) is not None

    def set_cooldown(self, piece_id, duration_ms):
        self._cooldowns[piece_id] = (self._clock, self._clock + duration_ms)

    def rest_remaining_fraction(self, piece_id):
        entry = self._cooldowns.get(piece_id)
        if entry is None:
            return None
        start_time, end_time = entry
        if self._clock >= end_time:
            del self._cooldowns[piece_id]
            return None
        total = end_time - start_time
        if total <= 0:
            return 0.0
        return (end_time - self._clock) / total

    def is_jumping_on(self, cell):
        return any(jump.cell == cell for jump in self._active_jumps)

    def active_motions(self):
        return list(self._active_motions)

    def start_motion(self, piece, source, destination, duration_ms):
        start_time = self._clock
        arrival_time = self._clock + duration_ms
        self._active_motions.append(Motion(piece, source, destination, start_time, arrival_time))
        self._board.remove_piece(piece)

    def start_jump(self, cell, end_time):
        self._active_jumps.append(Jump(cell, end_time))

    def advance_time(self, ms):
        if ms < 0:
            raise ValueError(f"advance_time expects a non-negative duration, got {ms}")

        new_clock = self._clock + ms
        events = []

        for jump in self._active_jumps:
            if jump.end_time <= new_clock:
                piece = self._board.piece_at(jump.cell)
                if piece is not None:
                    events.append(JumpEndedEvent(piece_id=piece.id, cell=jump.cell))

        # Every arrival/collision due by new_clock is resolved in strict
        # chronological order (never insertion order), recomputed fresh
        # each iteration since resolving one can change what's next -
        # this makes the outcome independent of the wait() call granularity.
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
            # Exact simultaneous meeting between enemies: no well-defined
            # winner, so neither survives - a documented, deterministic
            # policy rather than an arbitrary tie-break (see tests).
            self._active_motions.remove(motion_a)
            self._active_motions.remove(motion_b)
            return [self._self_destroyed_event(motion_a, cell), self._self_destroyed_event(motion_b, cell)]

        early, late = (motion_a, motion_b) if time_a < time_b else (motion_b, motion_a)
        if same_color:
            late.truncate_before(cell)
            return []

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
            # Can only happen when a different motion beat this one to
            # their shared destination with a different arrival time (an
            # exact tie is already caught in _resolve_collision) - stop
            # one cell short, same as an in-transit collision.
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
        # An empty guarded cell must not intercept indiscriminately -
        # only a jump still actually defended by some piece counts.
        for jump in self._active_jumps:
            if jump.cell != motion.destination:
                continue
            defender = self._board.piece_at(jump.cell)
            if defender is not None and defender.color != piece.color:
                return True
        return False
