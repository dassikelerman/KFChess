from dataclasses import dataclass
from typing import List, Optional

from model.position import Position


@dataclass(frozen=True)
class ArrivalEvent:
    piece_id: str
    source: Position
    destination: Position
    captured_piece_id: Optional[str]
    king_captured: bool


ArrivalEvents = List[ArrivalEvent]


@dataclass(frozen=True)
class JumpEndedEvent:
    piece_id: str
    cell: Position


@dataclass(frozen=True)
class MoveResult:
    is_accepted: bool
    reason: str
