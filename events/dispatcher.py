from collections import defaultdict


class EventDispatcher:
    """Minimal pub/sub: publishers don't know who (if anyone) is
    listening, and listeners don't know who published - the seam future
    consumers (NetworkPublisher, ReplayRecorder, SoundSystem) attach to
    without GameEngine ever changing."""

    def __init__(self):
        self._subscribers = defaultdict(list)

    def subscribe(self, event_type, callback):
        self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type, callback):
        callbacks = self._subscribers.get(event_type)
        if callbacks is not None and callback in callbacks:
            callbacks.remove(callback)

    def publish(self, event):
        for callback in list(self._subscribers.get(type(event), [])):
            callback(event)
