import os
import sys

import constants
from client.client_app import ClientApp
from client.login import login
from client.snapshot_view import SnapshotView
from events.action_history import ActionHistory
from events.dispatcher import EventDispatcher
from events.score_tracker import ScoreTracker
from events.sound_system import SOUND_FILE_BY_EVENT, SoundSystem
from input.controller_builder import build_controller
from view.game_view import GameView
from view.piece_animations import AnimationLibrary


def _sound_paths():
    return {
        filename: os.path.join(constants.SOUNDS_DIR, filename)
        for filename in set(SOUND_FILE_BY_EVENT.values())
    }


def _build_client_app(ws_client, snapshot_view, game_snapshot, clock_ms):
    snapshot_view.update(game_snapshot, clock_ms)

    dispatcher = EventDispatcher()
    score_tracker = ScoreTracker(dispatcher)
    action_history = ActionHistory(dispatcher)
    sound_system = SoundSystem(dispatcher)

    view = GameView(
        constants.BOARD_IMAGE_PATH,
        constants.CELL_SIZE,
        game_snapshot.board_width,
        game_snapshot.board_height,
        AnimationLibrary(constants.PIECES_DIR),
        panel_width=constants.PANEL_WIDTH,
    )
    controller = build_controller(
        ws_client, snapshot_view, game_snapshot.board_width, game_snapshot.board_height,
        cell_size=constants.CELL_SIZE, x_offset=constants.PANEL_WIDTH,
    )

    return ClientApp(
        ws_client, snapshot_view, dispatcher, score_tracker, action_history,
        sound_system, _sound_paths(), view, controller,
    )


def run(ws_url):
    username, role, ws_client, game_snapshot, clock_ms = login(ws_url)
    print(f"Connected as {username} ({role})")

    snapshot_view = SnapshotView()
    app = _build_client_app(ws_client, snapshot_view, game_snapshot, clock_ms)
    app.run()


def main():
    if len(sys.argv) < 2:
        print("usage: python -m client.run <ws_url>")
        sys.exit(1)
    run(sys.argv[1])


if __name__ == "__main__":
    main()
