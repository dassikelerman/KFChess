from events.game_events import (
    CaptureEvent,
    GameOverEvent,
    IllegalActionEvent,
    MoveCompletedEvent,
    PromotionEvent,
)

SOUND_FILE_BY_EVENT = {
    MoveCompletedEvent: "move.wav",
    CaptureEvent: "capture.wav",
    PromotionEvent: "promotion.wav",
    GameOverEvent: "game_over.wav",
    IllegalActionEvent: "illegal_move.wav",
}


class SoundSystem:
    def __init__(self, dispatcher):
        self._pending = []
        dispatcher.subscribe(MoveCompletedEvent, self._on_move_completed)
        dispatcher.subscribe(CaptureEvent, self._on_capture)
        dispatcher.subscribe(PromotionEvent, self._on_promotion)
        dispatcher.subscribe(GameOverEvent, self._on_game_over)
        dispatcher.subscribe(IllegalActionEvent, self._on_illegal_action)

    def _on_move_completed(self, event):
        self._queue(MoveCompletedEvent)

    def _on_capture(self, event):
        self._queue(CaptureEvent)

    def _on_promotion(self, event):
        self._queue(PromotionEvent)

    def _on_game_over(self, event):
        self._queue(GameOverEvent)

    def _on_illegal_action(self, event):
        self._queue(IllegalActionEvent)

    def _queue(self, event_type):
        self._pending.append(SOUND_FILE_BY_EVENT[event_type])

    def drain_pending(self):
        pending = list(self._pending)
        self._pending.clear()
        return pending
