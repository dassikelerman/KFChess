import queue
import winsound

import cv2

import constants
from view.game_ui_snapshot import build_ui_snapshot


class ClientApp:
    def __init__(
        self, ws_client, snapshot_view, dispatcher, score_tracker, action_history,
        sound_system, sound_paths, view, controller,
    ):
        self._ws_client = ws_client
        self._snapshot_view = snapshot_view
        self._dispatcher = dispatcher
        self._score_tracker = score_tracker
        self._action_history = action_history
        self._sound_system = sound_system
        self._sound_paths = sound_paths
        self._view = view
        self._controller = controller

    def run(self):
        cv2.namedWindow(constants.WINDOW_NAME)
        cv2.setMouseCallback(
            constants.WINDOW_NAME, lambda event, x, y, flags, userdata: self._on_mouse(event, x, y)
        )

        while True:
            self._drain_inbound()
            self._controller.refresh_selection()

            for filename in self._sound_system.drain_pending():
                winsound.PlaySound(self._sound_paths[filename], winsound.SND_FILENAME | winsound.SND_ASYNC)

            ui_snapshot = build_ui_snapshot(
                self._snapshot_view, self._controller, self._score_tracker, self._action_history
            )
            frame = self._view.render(ui_snapshot)
            frame.show(constants.WINDOW_NAME)

            key = cv2.waitKey(constants.FRAME_POLL_MS) & 0xFF
            if key == constants.ESCAPE_KEY or cv2.getWindowProperty(constants.WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                break
            if self._snapshot_view.game_over:
                cv2.waitKey(0)
                break

        cv2.destroyAllWindows()

    def _drain_inbound(self):
        while True:
            try:
                item = self._ws_client.inbound.get_nowait()
            except queue.Empty:
                return

            kind = item[0]
            if kind == "snapshot":
                _, game_snapshot, clock_ms = item
                self._snapshot_view.update(game_snapshot, clock_ms)
            elif kind == "event":
                _, event = item
                self._dispatcher.publish(event)

    def _on_mouse(self, event, x, y):
        if event == cv2.EVENT_LBUTTONDOWN:
            self._controller.click(x, y)
        elif event == cv2.EVENT_RBUTTONDOWN:
            self._controller.jump(x, y)
