from dataclasses import dataclass

from model.piece import Piece
from model.position import Position


def _unit_step(delta):
    return (delta > 0) - (delta < 0)


@dataclass
class Motion:
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
        path = self.path_cells()
        index = path.index(cell)
        return self.start_time + (self.duration_ms / len(path)) * (index + 1)

    def truncate_before(self, cell: Position) -> None:
        path = self.path_cells()
        index = path.index(cell)
        per_cell_ms = self.duration_ms / len(path)
        new_destination = path[index - 1] if index > 0 else self.source
        new_arrival_time = self.start_time + round(per_cell_ms * index)
        self.destination = new_destination
        self.arrival_time = new_arrival_time


@dataclass
class Jump:
    cell: Position
    end_time: int
