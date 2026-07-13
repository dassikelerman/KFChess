from dataclasses import dataclass

from model.position import Position


@dataclass
class Motion:
    """An in-flight move: a piece travelling from source to destination
    over duration_ms. Holds piece_id rather than a live Piece, so a
    Motion never needs to touch the Board itself - only the arbiter that
    owns it does.
    """

    piece_id: str
    source: Position
    destination: Position
    duration_ms: int
    elapsed_ms: int = 0

    def advance(self, ms):
        self.elapsed_ms += ms

    @property
    def progress(self):
        if self.duration_ms <= 0:
            return 1.0
        return min(self.elapsed_ms / self.duration_ms, 1.0)

    @property
    def is_complete(self):
        return self.elapsed_ms >= self.duration_ms


@dataclass
class Jump:
    """An active jump/interception window guarding a cell until end_time."""

    cell: Position
    end_time: int
