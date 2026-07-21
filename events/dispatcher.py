from collections import defaultdict


class EventDispatcher:
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
