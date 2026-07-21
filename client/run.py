"""Client entry point, step 5 of the client/server migration
(docs/kf-chess-architecture-plan.md): connects, receives state, renders
it, and now sends real moves/jumps through the same Controller
view/run.py uses - WsClient satisfies ActionSink, SnapshotView
satisfies GameStateReader (both Protocols in input/controller.py).

Feature 3 (docs/kf-chess-architecture-plan.md): a plain, unauthenticated
username is collected from the terminal and sent as the very first
message, before the server will assign a role at all (server/session.py,
server/ws_server.py).

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
from input.controller_builder import build_controller
from view.game_ui_snapshot import build_ui_snapshot
from view.game_view import GameView
from view.piece_animations import AnimationLibrary


def _sound_paths():
    return {
        filename: os.path.join(constants.SOUNDS_DIR, filename)
        for filename in set(SOUND_FILE_BY_EVENT.values())
    }


def _prompt_for_username():
    username = ""
    while not username:
        username = input("Username: ").strip()
    return username


def run(ws_url):
    username = _prompt_for_username()

    dispatcher = EventDispatcher()
    score_tracker = ScoreTracker(dispatcher)
    action_history = ActionHistory(dispatcher)
    sound_system = SoundSystem(dispatcher)
    sound_paths = _sound_paths()

    snapshot_view = SnapshotView()

    ws_client = WsClient(ws_url)
    ws_client.start()
    ws_client.send_login(username)

    # GameView needs board dimensions up front, same as GameEngine's own
    # board does locally in view/run.py - here that only exists once the
    # server's first snapshot arrives, so block for it before building
    # the window at all. The server sends a "role" message first
    # (server/ws_server.py, right after a successful login) - captured
    # here too so it can be printed below.
    role = None
    game_snapshot = None
    while game_snapshot is None:
        item = ws_client.inbound.get()
        if item[0] == "snapshot":
            _, game_snapshot, clock_ms = item
        elif item[0] == "role":
            _, role = item
    snapshot_view.update(game_snapshot, clock_ms)

    print(f"Connected as {username} ({role})")

    view = GameView(
        constants.BOARD_IMAGE_PATH,
        constants.CELL_SIZE,
        game_snapshot.board_width,
        game_snapshot.board_height,
        AnimationLibrary(constants.PIECES_DIR),
        panel_width=constants.PANEL_WIDTH,
    )

    # Same click-to-cell mapping view/run.py builds locally - the client
    # reads state through snapshot_view instead of a real GameEngine, and
    # sends actions through ws_client instead of calling the engine
    # directly, but Controller itself doesn't know the difference.
    controller = build_controller(
        ws_client, snapshot_view, game_snapshot.board_width, game_snapshot.board_height,
        cell_size=constants.CELL_SIZE, x_offset=constants.PANEL_WIDTH,
    )

    cv2.namedWindow(constants.WINDOW_NAME)
    cv2.setMouseCallback(
        constants.WINDOW_NAME, lambda event, x, y, flags, userdata: _on_mouse(controller, event, x, y)
    )

    while True:
        _drain_inbound(ws_client, snapshot_view, dispatcher)
        controller.refresh_selection()

        for filename in sound_system.drain_pending():
            winsound.PlaySound(sound_paths[filename], winsound.SND_FILENAME | winsound.SND_ASYNC)

        ui_snapshot = build_ui_snapshot(snapshot_view, controller, score_tracker, action_history)
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
        # A "role" item never arrives here - it's sent once, up front, and
        # already consumed by the initial wait loop above.


def _on_mouse(controller, event, x, y):
    if event == cv2.EVENT_LBUTTONDOWN:
        controller.click(x, y)
    elif event == cv2.EVENT_RBUTTONDOWN:
        controller.jump(x, y)


def main():
    if len(sys.argv) < 2:
        print("usage: python -m client.run <ws_url>")
        sys.exit(1)
    run(sys.argv[1])


if __name__ == "__main__":
    main()
