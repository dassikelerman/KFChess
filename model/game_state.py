from dataclasses import dataclass
from enum import Enum
from typing import Optional

from model.piece import PieceColor, PieceKind
from model.position import Position


@dataclass(frozen=True)
class ArrivalEvent:
    piece_id: str
    source: Position
    destination: Position
    captured_piece_id: Optional[str]
    king_captured: bool
    piece_kind: Optional[PieceKind] = None
    piece_color: Optional[PieceColor] = None
    captured_kind: Optional[PieceKind] = None
    captured_color: Optional[PieceColor] = None


@dataclass(frozen=True)
class JumpEndedEvent:
    piece_id: str
    cell: Position
    piece_kind: Optional[PieceKind] = None
    piece_color: Optional[PieceColor] = None


class ActionResultReason(Enum):
    OK = "ok"
    GAME_OVER = "game_over"
    JUMP_IN_PROGRESS = "jump_in_progress"
    RESTING = "resting"
    EMPTY_SOURCE = "empty_source"
    FRIENDLY_DESTINATION = "friendly_destination"
    ILLEGAL_PIECE_MOVE = "illegal_piece_move"


@dataclass(frozen=True)
class ActionResult:
    is_accepted: bool
    reason: ActionResultReason
