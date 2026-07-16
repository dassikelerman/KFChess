from dataclasses import dataclass
from typing import List, Optional

from model.piece import PieceColor, PieceKind
from model.position import Position


@dataclass(frozen=True)
class ArrivalEvent:
    piece_id: str
    source: Position
    destination: Position
    captured_piece_id: Optional[str]
    king_captured: bool
    # Populated by RealTimeArbiter at the same point captured_piece_id is
    # decided, since the mover/victim Piece objects become unreliable to
    # look up later (still in flight, already moved, or already gone) -
    # see GameEngine's rich, outward-facing events in events/game_events.py.
    piece_kind: Optional[PieceKind] = None
    piece_color: Optional[PieceColor] = None
    captured_kind: Optional[PieceKind] = None
    captured_color: Optional[PieceColor] = None


ArrivalEvents = List[ArrivalEvent]


@dataclass(frozen=True)
class JumpEndedEvent:
    piece_id: str
    cell: Position
    piece_kind: Optional[PieceKind] = None
    piece_color: Optional[PieceColor] = None


@dataclass(frozen=True)
class MoveResult:
    is_accepted: bool
    reason: str
