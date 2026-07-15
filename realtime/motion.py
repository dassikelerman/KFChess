from dataclasses import dataclass

from model.piece import Piece
from model.position import Position


def _unit_step(delta):
    return (delta > 0) - (delta < 0)


@dataclass
class Motion:
    """An in-flight move: a piece travelling from source to destination,
    due to land at arrival_time on the arbiter's absolute clock.

    Holds the full departed Piece rather than just its id: the moment a
    Motion starts, the piece leaves the Board entirely (see
    RealTimeArbiter.start_motion) and travels only as part of this
    Motion, so this is the one place its identity/color/kind lives while
    it's airborne - nothing else can capture or displace it at its old
    cell in the meantime.

    start_time/arrival_time are absolute clock values rather than a
    relative duration, so completion and resolution order are judged by
    when a motion actually lands, not by the order motions happened to
    be queued in (see RealTimeArbiter.advance_time). destination (and
    arrival_time with it) can be shortened mid-flight by a same-color
    in-transit collision - see truncate_before().
    """

    piece: Piece
    source: Position
    destination: Position
    start_time: int
    arrival_time: int

    @property
    def piece_id(self):
        return self.piece.id

    @property
    def duration_ms(self):
        return self.arrival_time - self.start_time

    def is_complete_at(self, current_time: int) -> bool:
        return current_time >= self.arrival_time

    def progress_at(self, current_time: int) -> float:
        total = self.arrival_time - self.start_time
        if total <= 0:
            return 1.0
        return min(max((current_time - self.start_time) / total, 0.0), 1.0)

    def path_cells(self):
        """Cells this motion passes through, in travel order, starting
        just after source and ending at (the current) destination.
        source itself is excluded - the piece already logically left it
        the instant the motion started.

        A straight horizontal/vertical/diagonal move (every piece kind
        except a knight's L-shape) yields every intermediate cell, for
        in-transit collision detection. A knight's move isn't a line
        it travels along - it already ignores blockers for legality
        purposes - so it has no meaningful intermediate cells: only the
        destination itself is returned.
        """
        dr = self.destination.row - self.source.row
        dc = self.destination.col - self.source.col
        if dr == 0 and dc == 0:
            return []
        if dr == 0 or dc == 0 or abs(dr) == abs(dc):
            distance = max(abs(dr), abs(dc))
            step_r, step_c = _unit_step(dr), _unit_step(dc)
            return [
                Position(self.source.row + step_r * i, self.source.col + step_c * i)
                for i in range(1, distance + 1)
            ]
        return [self.destination]

    def time_at_cell(self, cell: Position) -> float:
        """Absolute clock time this motion reaches `cell` - must be one
        of path_cells(). Constant speed per cell along the path."""
        path = self.path_cells()
        index = path.index(cell)
        return self.start_time + (self.duration_ms / len(path)) * (index + 1)

    def truncate_before(self, cell: Position) -> None:
        """Redirects this motion to stop one cell short of `cell` - used
        when a same-color in-transit collision means this motion can't
        pass through/land on a cell another friendly motion reached
        first. The new destination is the last cell this motion would
        have reached before `cell`, or its own source if `cell` was the
        very first step (in which case it ends up going nowhere).
        Preserves this motion's per-cell speed when recomputing
        arrival_time.
        """
        path = self.path_cells()
        index = path.index(cell)
        per_cell_ms = self.duration_ms / len(path)
        new_destination = path[index - 1] if index > 0 else self.source
        new_arrival_time = self.start_time + round(per_cell_ms * index)
        self.destination = new_destination
        self.arrival_time = new_arrival_time


@dataclass
class Jump:
    """An active jump/interception window guarding a cell until end_time."""

    cell: Position
    end_time: int
