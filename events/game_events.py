from dataclasses import dataclass
from typing import Optional

from model.piece import PieceColor, PieceKind
from model.position import Position


@dataclass(frozen=True)
class MoveCompletedEvent:
    piece_id: str
    piece_kind: PieceKind
    piece_color: PieceColor
    destination: Position
    at_ms: int


@dataclass(frozen=True)
class CaptureEvent:
    piece_id: str
    piece_kind: PieceKind
    piece_color: PieceColor
    captured_piece_id: str
    captured_kind: PieceKind
    captured_color: PieceColor
    at: Position
    at_ms: int


@dataclass(frozen=True)
class JumpCompletedEvent:
    piece_id: str
    piece_kind: PieceKind
    piece_color: PieceColor
    cell: Position
    at_ms: int


@dataclass(frozen=True)
class MotionStoppedEvent:
    piece_id: str
    piece_kind: PieceKind
    piece_color: PieceColor
    at: Position
    at_ms: int


@dataclass(frozen=True)
class PromotionEvent:
    piece_id: str
    piece_color: PieceColor
    from_kind: PieceKind
    to_kind: PieceKind
    at: Position
    at_ms: int


@dataclass(frozen=True)
class GameOverEvent:
    winner_color: Optional[PieceColor]
    at_ms: int


@dataclass(frozen=True)
class IllegalActionEvent:
    piece_id: Optional[str]
    destination: Position
    at_ms: int
