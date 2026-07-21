"""Step 6 of the client/server migration (docs/kf-chess-architecture-plan.md):
broadcasts every outward domain game event to all connected clients,
and unicasts IllegalActionEvent to just the connection that triggered
it - a rejection is only meaningful to the one client that attempted
it; broadcasting it to everyone else would be noise (and would leak
what another player attempted). Subscribes to the Session's dispatcher
the same way ScoreTracker/ActionHistory/SoundSystem already do -
broadcast_fn/unicast_fn are both injected, so this class knows nothing
about websockets or connections itself."""

from events.game_events import (
    CaptureEvent,
    GameOverEvent,
    JumpCompletedEvent,
    MotionStoppedEvent,
    MoveCompletedEvent,
    PromotionEvent,
)
from events.serialization import to_dict

# IllegalActionEvent is deliberately not in this list - it's never
# broadcast, only unicast (see server/session.py, which builds and
# unicasts it directly rather than relying on the dispatcher).
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
