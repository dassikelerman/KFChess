from events.game_events import (
    CaptureEvent,
    GameOverEvent,
    JumpCompletedEvent,
    MotionStoppedEvent,
    MoveCompletedEvent,
    PromotionEvent,
)
from events.serialization import to_dict

# IllegalActionEvent is unicast-only, never broadcast (see server/session.py).
_BROADCAST_EVENT_TYPES = (
    MoveCompletedEvent,
    CaptureEvent,
    JumpCompletedEvent,
    MotionStoppedEvent,
    PromotionEvent,
    GameOverEvent,
)


class NetworkPublisher:
    def __init__(self, dispatcher, broadcast_fn, unicast_fn):
        self._broadcast_fn = broadcast_fn
        self._unicast_fn = unicast_fn
        for event_type in _BROADCAST_EVENT_TYPES:
            dispatcher.subscribe(event_type, self._on_event)

    def _on_event(self, event):
        self._broadcast_fn(to_dict(event))

    def unicast(self, connection, event):
        self._unicast_fn(connection, to_dict(event))
