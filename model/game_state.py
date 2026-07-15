from dataclasses import dataclass
from typing import List, Optional

from model.piece import AnimationState, PieceColor, PieceState
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
    directly.

    row/col are the piece's logical cell (an in-flight piece still shows
    its source here, same as Board - see RealTimeArbiter). render_row/
    render_col are the visual position for animation: identical to row/col
    when idle, linearly interpolated between a motion's source and
    destination while one is active. animation_state is derived similarly
    - see GameEngine.snapshot(). rest_fraction_remaining is None unless
    the piece is currently in a post-move/post-jump cooldown, in which
    case it's a fraction from 1.0 (just started) down to just above 0.0
    (about to finish) - purely for rendering a fading cooldown indicator.
    """

    id: str
    kind: object  # PieceKind, or a raw custom-kind letter - see model.piece.parse_kind
    color: PieceColor
    state: PieceState
    row: int
    col: int
    render_row: float
    render_col: float
    animation_state: AnimationState
    rest_fraction_remaining: Optional[float]


@dataclass(frozen=True)
class GameSnapshot:
    """A read-only, point-in-time view of the whole game, suitable for
    rendering without touching GameEngine's live collaborators."""

    board_width: int
    board_height: int
    pieces: List[PieceSnapshot]
    game_over: bool
