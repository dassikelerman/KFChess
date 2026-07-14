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
    """

    def __init__(self, board):
        self._board = board
        self._clock = 0
        self._active_motions = []
        self._active_jumps = []

    @property
    def clock(self):
        return self._clock

    def has_active_motion(self, cell=None):
        if cell is None:
            return bool(self._active_motions)
        return any(
            motion.source == cell and self._motion_piece_still_there(motion)
            for motion in self._active_motions
        )

    def _motion_piece_still_there(self, motion):
        # A motion queued from `cell` can be left stale if the piece that
        # queued it was captured on that very cell by another motion's
        # arrival in the meantime (e.g. an enemy motion whose destination
        # is this motion's still-pending source) - the cell it "blocks"
        # may now hold a different, perfectly idle piece. Same identity
        # check _resolve_arrival() already relies on.
        piece = self._board.piece_at(motion.source)
        return piece is not None and piece.id == motion.piece_id

    def is_jumping_on(self, cell):
        return any(jump.cell == cell for jump in self._active_jumps)

    def active_motion_for(self, piece_id):
        """The Motion currently in flight for this piece, or None -
        read-only lookup by identity (never by cell; see has_active_motion)
        for callers like GameEngine.snapshot() that need to render a
        specific piece's progress without reaching into _active_motions."""
        return next((m for m in self._active_motions if m.piece_id == piece_id), None)

    def active_jump_for(self, cell):
        """The Jump currently guarding this cell, or None - Jump is
        deliberately cell-based rather than tied to a piece's identity
        (see is_jumping_on), so this is keyed by cell too."""
        return next((j for j in self._active_jumps if j.cell == cell), None)

    def start_motion(self, piece, source, destination, duration_ms):
        start_time = self._clock
        arrival_time = self._clock + duration_ms
        self._active_motions.append(Motion(piece.id, source, destination, start_time, arrival_time))

    def start_jump(self, cell, end_time):
        self._active_jumps.append(Jump(cell, end_time))

    def advance_time(self, ms):
        
        if ms < 0:
            raise ValueError(f"advance_time expects a non-negative duration, got {ms}")

        self._clock += ms

        overdue = [m for m in self._active_motions if m.is_complete_at(self._clock)]
        remaining = [m for m in self._active_motions if not m.is_complete_at(self._clock)]

        # Resolve strictly by arrival time, not by insertion order into
        # _active_motions - a motion queued later can still have the
        # earlier arrival_time (e.g. a short move queued after a long
        # one), and both must land in real arrival order. sort() is
        # stable, so motions that tie on arrival_time keep their
        # relative insertion order; that's a deliberate, documented
        # fallback rather than a resolved game rule - simultaneous
        # arrivals still need an explicit policy if that ever matters.
        overdue.sort(key=lambda motion: motion.arrival_time)

        events = []
        for motion in overdue:
            event = self._resolve_arrival(motion)
            if event is not None:
                events.append(event)

        self._active_motions = remaining
        self._active_jumps = [j for j in self._active_jumps if self._clock < j.end_time]
        return events

    def _resolve_arrival(self, motion):
        piece = self._board.piece_at(motion.source)
        if piece is None or piece.id != motion.piece_id:
            # The piece that queued this motion was already captured this
            # same tick by another motion resolving first (e.g. a head-on
            # swap, where this motion's source is the other motion's
            # destination). That capture was already reported via the
            # other motion's own ArrivalEvent, so this motion simply
            # fizzles: nothing to move, nothing new to report.
            return None

        if self._is_intercepted(motion, piece):
            self._board.remove_piece(piece)
            return ArrivalEvent(
                piece_id=motion.piece_id,
                source=motion.source,
                destination=motion.destination,
                captured_piece_id=piece.id,
                king_captured=piece.kind == PieceKind.KING,
            )

        target = self._board.piece_at(motion.destination)
        if target is not None and target.color == piece.color:
            return None

        captured_piece_id = None if target is None else target.id
        king_captured = target is not None and target.kind == PieceKind.KING

        self._board.move_piece(piece, motion.destination)

        return ArrivalEvent(
            piece_id=motion.piece_id,
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
