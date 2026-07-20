"""Step 3 of the client/server migration (docs/kf-chess-architecture-plan.md):
broadcasts every outward game event to connected clients. Subscribes to
the Session's dispatcher the same way ScoreTracker/ActionHistory/
SoundSystem already do - broadcast_fn is injected, so this class knows
nothing about websockets or connections itself. Broadcast-only for now;
unicast (for events like IllegalActionEvent that should reach only the
connection that triggered them) is a later step."""

from events.game_events import (
    CaptureEvent,
    GameOverEvent,
    IllegalActionEvent,
    JumpCompletedEvent,
    MotionStoppedEvent,
    MoveCompletedEvent,
    PromotionEvent,
)
from events.serialization import to_dict

_EVENT_TYPES = (
    MoveCompletedEvent,
    CaptureEvent,
    JumpCompletedEvent,
    MotionStoppedEvent,
    PromotionEvent,
    GameOverEvent,
    IllegalActionEvent,
)


class NetworkPublisher:
    def __init__(self, dispatcher, broadcast_fn):
        self._broadcast_fn = broadcast_fn
        for event_type in _EVENT_TYPES:
            dispatcher.subscribe(event_type, self._on_event)

    def _on_event(self, event):
        self._broadcast_fn(to_dict(event))

    def snapshot_payload(self, components):
        return to_dict(components.engine.snapshot())
