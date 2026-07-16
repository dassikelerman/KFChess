from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from engine.snapshot import GameSnapshot
from events.action_history import ActionEntry
from model.piece import PieceColor


@dataclass(frozen=True)
class GameUiSnapshot:
    """Everything GameView needs to draw one frame, aggregated in a
    single object so render() takes one argument instead of a growing
    parameter list. Purely a read-only view-layer aggregate - none of
    this lives in GameEngine or GameSnapshot."""

    game: GameSnapshot
    clock_ms: int
    selected: Optional[Tuple[int, int]]
    score: Dict[PieceColor, int]
    recent_actions: List[ActionEntry]


def build_ui_snapshot(engine, controller, score_tracker, action_history, recent_action_count=None):
    recent_actions = (
        action_history.recent() if recent_action_count is None
        else action_history.recent(recent_action_count)
    )
    return GameUiSnapshot(
        game=engine.snapshot(),
        clock_ms=engine.clock,
        selected=controller.selected,
        score=score_tracker.snapshot(),
        recent_actions=recent_actions,
    )
