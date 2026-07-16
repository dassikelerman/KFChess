from dataclasses import dataclass
from typing import Optional

from model.piece import PieceColor, PieceKind
from model.position import Position

# Rich, outward-facing game-level events - distinct from the internal
# ArrivalEvent/JumpEndedEvent RealTimeArbiter reports to GameEngine.
# GameEngine only ever publishes one of these once it has already
# verified the underlying arrival is real (post identity-guard, post
# win-condition check) - see GameEngine._publish_action_event.


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
    # A piece's own motion ended by destruction rather than a landing -
    # intercepted by a jump guard, or an exact-tie mutual collision. No
    # distinct capturer is identifiable from the arbiter's own event, so
    # this is reported as the piece's motion stopping, not as a Capture.
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
