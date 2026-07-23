"""NetworkPublisher: bridge one room's event dispatcher onto the network.

A GameSession publishes plain domain events (a move landed, a piece was captured, someone
disconnected...) without knowing anyone is listening over a socket. One NetworkPublisher
per room subscribes to the broadcast-worthy event types and turns each into a wire
payload sent to every connection in that room; IllegalActionEvent is never broadcast -
GameSession unicasts it straight to the one connection whose action was rejected.
"""

from events.game_events import (
    CaptureEvent,
    GameOverEvent,
    JumpCompletedEvent,
    MotionStoppedEvent,
    MoveCompletedEvent,
    PlayerDisconnectedEvent,
    PlayerReconnectedEvent,
    PromotionEvent,
)
from protocol.registry import message_to_payload

# IllegalActionEvent is unicast-only, never broadcast (see server/session.py).
_BROADCAST_EVENT_TYPES = (
    MoveCompletedEvent,
    CaptureEvent,
    JumpCompletedEvent,
    MotionStoppedEvent,
    PromotionEvent,
    GameOverEvent,
    PlayerDisconnectedEvent,
    PlayerReconnectedEvent,
)


class NetworkPublisher:
    def __init__(self, dispatcher, broadcast_fn, unicast_fn):
        self._broadcast_fn = broadcast_fn
        self._unicast_fn = unicast_fn
        for event_type in _BROADCAST_EVENT_TYPES:
            dispatcher.subscribe(event_type, self._on_event)

    def _on_event(self, event):
        self._broadcast_fn(message_to_payload(event))

    def unicast(self, connection, event):
        self._unicast_fn(connection, message_to_payload(event))
