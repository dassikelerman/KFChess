"""GameWindow: the connected game window's frame loop.

Runs no engine of its own - the server owns the game. Each frame it drains the
connection's inbound queue (snapshots update SnapshotView, events go on the dispatcher
for the score/log/sound subscribers already wired up by client/run.py), renders, and
turns clicks into move/jump requests sent back through the connection. Paired with
LobbyView by name as much as by behavior: LobbyView is the window you see before a game,
GameWindow is the one you see once you're in it.
"""

import logging
import queue
import winsound

import cv2

import constants
from client.server_connection import EventReceived, SnapshotReceived
from events.game_events import GameOverEvent, PlayerDisconnectedEvent, PlayerReconnectedEvent
from view.game_ui_snapshot import build_ui_snapshot

logger = logging.getLogger(__name__)


class SnapshotView:
    def __init__(self):
        self._snapshot = None
        self._clock_ms = 0

    def update(self, game_snapshot, clock_ms):
        self._snapshot = game_snapshot
        self._clock_ms = clock_ms

    def snapshot(self):
        return self._snapshot

    @property
    def clock(self):
        return self._clock_ms

    @property
    def game_over(self):
        return self._snapshot is not None and self._snapshot.game_over

    def piece_at(self, position):
        for piece in self._pieces():
            if piece.row == position.row and piece.col == position.col:
                return piece
        return None

    def is_busy(self, position):
        piece = self.piece_at(position)
        return piece is not None and piece.is_jumping

    def _pieces(self):
        return [] if self._snapshot is None else self._snapshot.pieces


class GameWindow:
    def __init__(
        self, connection, snapshot_view, dispatcher, score_tracker, action_history,
        sound_system, sound_paths, view, controller, room_id=None,
    ):
        self._connection = connection
        self._snapshot_view = snapshot_view
        self._dispatcher = dispatcher
        self._score_tracker = score_tracker
        self._action_history = action_history
        self._sound_system = sound_system
        self._sound_paths = sound_paths
        self._view = view
        self._controller = controller
        self._room_id = room_id
        self._disconnect_warning = None
        self._dispatcher.subscribe(PlayerDisconnectedEvent, self._on_player_disconnected)
        self._dispatcher.subscribe(PlayerReconnectedEvent, self._on_player_reconnected)
        self._dispatcher.subscribe(GameOverEvent, self._on_game_over)

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
            if self._room_id is not None:
                cv2.putText(
                    frame.img, f"Room: {self._room_id}", (10, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2, cv2.LINE_AA,
                )
            if self._disconnect_warning is not None:
                cv2.putText(
                    frame.img, self._disconnect_warning, (10, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2, cv2.LINE_AA,
                )
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
                item = self._connection.inbound.get_nowait()
            except queue.Empty:
                return

            if isinstance(item, SnapshotReceived):
                self._snapshot_view.update(item.game_snapshot, item.clock_ms)
            elif isinstance(item, EventReceived):
                self._dispatcher.publish(item.event)

    def _on_player_disconnected(self, event):
        if self._disconnect_warning is None:  # log only the transition, not every tick
            logger.info("opponent disconnected: color=%s", event.color)
        self._disconnect_warning = f"Opponent disconnected - resigning in {event.seconds_remaining}s"

    def _on_player_reconnected(self, event):
        logger.info("opponent reconnected: color=%s", event.color)
        self._disconnect_warning = None

    def _on_game_over(self, event):
        logger.info("game over: winner_color=%s", event.winner_color)
        self._disconnect_warning = None

    def _on_mouse(self, event, x, y):
        if event == cv2.EVENT_LBUTTONDOWN:
            self._controller.click(x, y)
        elif event == cv2.EVENT_RBUTTONDOWN:
            self._controller.jump(x, y)
