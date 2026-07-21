from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from engine.snapshot import GameSnapshot
from events.action_history import ActionEntry
from model.piece import PieceColor


@dataclass(frozen=True)
class GameUiSnapshot:
    game: GameSnapshot
    clock_ms: int
    selected: Optional[Tuple[int, int]]
    score: Dict[PieceColor, int]
    recent_actions: List[ActionEntry]


def build_ui_snapshot(state_source, controller, score_tracker, action_history, recent_action_count=None):
    recent_actions = (
        action_history.recent() if recent_action_count is None
        else action_history.recent(recent_action_count)
    )
    return GameUiSnapshot(
        game=state_source.snapshot(),
        clock_ms=state_source.clock,
        selected=controller.selected,
        score=score_tracker.snapshot(),
        recent_actions=recent_actions,
    )
