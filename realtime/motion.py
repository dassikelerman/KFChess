from dataclasses import dataclass

from model.position import Position


@dataclass
class Motion:
    """An in-flight move: a piece travelling from source to destination,
    due to land at arrival_time on the arbiter's absolute clock. Holds
    piece_id rather than a live Piece, so a Motion never needs to touch
    the Board itself - only the arbiter that owns it does.

    start_time/arrival_time are absolute clock values rather than a
    relative duration, so completion and resolution order are judged by
    when a motion actually lands, not by the order motions happened to
    be queued in (see RealTimeArbiter.advance_time).
    """

    piece_id: str
    source: Position
    destination: Position
    start_time: int
    arrival_time: int

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


@dataclass
class Jump:
    """An active jump/interception window guarding a cell until end_time."""

    cell: Position
    end_time: int
