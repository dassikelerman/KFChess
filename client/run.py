"""Client entry point, step 4 of the client/server migration
(docs/kf-chess-architecture-plan.md): connects, receives state, and
renders it. No mouse handling and no move/jump sending yet - Controller
isn't wired in until Step 5, so there's no cv2.setMouseCallback here.

Run as a module from the project root: python -m client.run <ws_url>
"""

import os
import queue
import sys
import winsound

import cv2

import constants
from client.snapshot_view import SnapshotView
from client.ws_client import WsClient
from events.action_history import ActionHistory
from events.dispatcher import EventDispatcher
from events.score_tracker import ScoreTracker
from events.sound_system import SOUND_FILE_BY_EVENT, SoundSystem
from view.game_ui_snapshot import GameUiSnapshot
from view.game_view import GameView
from view.piece_animations import AnimationLibrary


def _sound_paths():
    return {
        filename: os.path.join(constants.SOUNDS_DIR, filename)
        for filename in set(SOUND_FILE_BY_EVENT.values())
    }


def run(ws_url):
    dispatcher = EventDispatcher()
    score_tracker = ScoreTracker(dispatcher)
    action_history = ActionHistory(dispatcher)
    sound_system = SoundSystem(dispatcher)
    sound_paths = _sound_paths()

    snapshot_view = SnapshotView()

    ws_client = WsClient(ws_url)
    ws_client.start()

    # GameView needs board dimensions up front, same as GameEngine's own
    # board does locally in view/run.py - here that only exists once the
    # server's first snapshot arrives, so block for it before building
    # the window at all. The server sends a "role" message first
    # (server/ws_server.py); it's not acted on yet since Controller/
    # ownership isn't wired in until Step 5, so it's skipped here too.
    game_snapshot = None
    while game_snapshot is None:
        item = ws_client.inbound.get()
        if item[0] == "snapshot":
            _, game_snapshot, clock_ms = item
    snapshot_view.update(game_snapshot, clock_ms)

    view = GameView(
        constants.BOARD_IMAGE_PATH,
        constants.CELL_SIZE,
        game_snapshot.board_width,
        game_snapshot.board_height,
        AnimationLibrary(constants.PIECES_DIR),
        panel_width=constants.PANEL_WIDTH,
    )

    cv2.namedWindow(constants.WINDOW_NAME)

    while True:
        _drain_inbound(ws_client, snapshot_view, dispatcher)

        for filename in sound_system.drain_pending():
            winsound.PlaySound(sound_paths[filename], winsound.SND_FILENAME | winsound.SND_ASYNC)

        ui_snapshot = GameUiSnapshot(
            game=snapshot_view.snapshot(),
            clock_ms=snapshot_view.clock,
            selected=None,
            score=score_tracker.snapshot(),
            recent_actions=action_history.recent(),
        )
        frame = view.render(ui_snapshot)
        frame.show(constants.WINDOW_NAME)

        key = cv2.waitKey(constants.FRAME_POLL_MS) & 0xFF
        if key == constants.ESCAPE_KEY or cv2.getWindowProperty(constants.WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
            break
        if snapshot_view.game_over:
            cv2.waitKey(0)
            break

    cv2.destroyAllWindows()


def _drain_inbound(ws_client, snapshot_view, dispatcher):
    while True:
        try:
            item = ws_client.inbound.get_nowait()
        except queue.Empty:
            return

        kind = item[0]
        if kind == "snapshot":
            _, game_snapshot, clock_ms = item
            snapshot_view.update(game_snapshot, clock_ms)
        elif kind == "event":
            _, event = item
            dispatcher.publish(event)
        # "role" items aren't acted on yet - Step 5 wires ownership.


def main():
    if len(sys.argv) < 2:
        print("usage: python -m client.run <ws_url>")
        sys.exit(1)
    run(sys.argv[1])


if __name__ == "__main__":
    main()
