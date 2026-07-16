from dataclasses import dataclass
from typing import Optional

from model.piece import PieceColor, kind_letter

from events.game_events import (
    CaptureEvent,
    GameOverEvent,
    JumpCompletedEvent,
    MotionStoppedEvent,
    MoveCompletedEvent,
    PromotionEvent,
)

DEFAULT_RECENT_COUNT = 30


def _token(color, kind):
    return color.value + kind_letter(kind)


@dataclass(frozen=True)
class ActionEntry:
    text: str
    # Which side's panel this belongs to; None means "show on both" -
    # only GameOverEvent (not tied to a single mover) uses that.
    color: Optional[PieceColor]
    at_ms: int


class ActionHistory:
    """Only real, already-verified occurrences are recorded here - never
    rejected/illegal move or jump attempts (those never reach GameEngine
    as an event in the first place)."""

    def __init__(self, dispatcher):
        self._entries = []
        dispatcher.subscribe(MoveCompletedEvent, self._on_move_completed)
        dispatcher.subscribe(CaptureEvent, self._on_capture)
        dispatcher.subscribe(JumpCompletedEvent, self._on_jump_completed)
        dispatcher.subscribe(MotionStoppedEvent, self._on_motion_stopped)
        dispatcher.subscribe(PromotionEvent, self._on_promotion)
        dispatcher.subscribe(GameOverEvent, self._on_game_over)

    def _on_move_completed(self, event):
        self._append(
            f"{_token(event.piece_color, event.piece_kind)} moved to {event.destination}",
            event.piece_color, event.at_ms,
        )

    def _on_capture(self, event):
        self._append(
            f"{_token(event.piece_color, event.piece_kind)} captured "
            f"{_token(event.captured_color, event.captured_kind)}",
            event.piece_color, event.at_ms,
        )

    def _on_jump_completed(self, event):
        self._append(
            f"{_token(event.piece_color, event.piece_kind)} jump completed",
            event.piece_color, event.at_ms,
        )

    def _on_motion_stopped(self, event):
        self._append(
            f"{_token(event.piece_color, event.piece_kind)} motion stopped",
            event.piece_color, event.at_ms,
        )

    def _on_promotion(self, event):
        self._append(
            f"{_token(event.piece_color, event.from_kind)} promoted to "
            f"{_token(event.piece_color, event.to_kind)}",
            event.piece_color, event.at_ms,
        )

    def _on_game_over(self, event):
        winner = event.winner_color.value if event.winner_color is not None else "?"
        self._append(f"Game over - {winner} wins", None, event.at_ms)

    def _append(self, text, color, at_ms):
        self._entries.append(ActionEntry(text=text, color=color, at_ms=at_ms))

    def entries(self):
        return list(self._entries)

    def recent(self, count=DEFAULT_RECENT_COUNT):
        return self._entries[-count:]
