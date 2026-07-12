from dataclasses import dataclass
from typing import List, Optional

from model.piece import PieceColor, PieceState
from model.position import Position


@dataclass(frozen=True)
class ArrivalEvent:
    """Reports what happened when a Motion completed: which piece
    arrived, what (if anything) it captured, and whether that capture
    was a king - a fact only. Deciding whether that ends the game is up
    to whoever consumes the event, not the reporter.
    """

    piece_id: str
    source: Position
    destination: Position
    captured_piece_id: Optional[str]
    king_captured: bool


ArrivalEvents = List[ArrivalEvent]


@dataclass(frozen=True)
class MoveResult:
    """The outcome of a GameEngine.request_move() call - a UI-facing
    result the caller (e.g. Controller) can check without knowing
    anything about RuleEngine's own reason vocabulary.
    """

    is_accepted: bool
    reason: str


@dataclass(frozen=True)
class PieceSnapshot:
    """A read-only, board-independent view of one piece, for renderers
    or other consumers that shouldn't need to talk to Board/Position
    directly."""

    id: str
    kind: object  # PieceKind - see model.piece.parse_kind
    color: PieceColor
    state: PieceState
    row: int
    col: int


@dataclass(frozen=True)
class GameSnapshot:
    """A read-only, point-in-time view of the whole game, suitable for
    rendering without touching GameEngine's live collaborators."""

    board_width: int
    board_height: int
    pieces: List[PieceSnapshot]
    selected_cell: Optional[Position]
    game_over: bool
