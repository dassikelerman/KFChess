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
        return any(motion.source == cell for motion in self._active_motions)

    def is_jumping_on(self, cell):
        return any(jump.cell == cell for jump in self._active_jumps)

    def opposite_color_moving(self, color):
        return any(
            self._piece_color(motion.source) != color for motion in self._active_motions
        )

    def start_motion(self, piece, source, destination, duration_ms):
        self._active_motions.append(Motion(piece.id, source, destination, duration_ms))

    def start_jump(self, piece, cell, end_time):
        self._active_jumps.append(Jump(piece.id, cell, end_time))

    def advance_time(self, ms):
        self._clock += ms
        for motion in self._active_motions:
            motion.advance(ms)

        remaining = []
        events = []
        for motion in self._active_motions:
            if not motion.is_complete:
                remaining.append(motion)
                continue
            event = self._resolve_arrival(motion)
            if event is not None:
                events.append(event)
        self._active_motions = remaining
        self._active_jumps = [j for j in self._active_jumps if self._clock < j.end_time]
        return events

    def _resolve_arrival(self, motion):
        piece = self._board.piece_at(motion.source)

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
        return any(
            jump.cell == motion.destination and self._piece_color(jump.cell) != piece.color
            for jump in self._active_jumps
        )

    def _piece_color(self, cell):
        piece = self._board.piece_at(cell)
        return piece.color if piece is not None else None
