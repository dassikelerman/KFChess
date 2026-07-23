"""Client entry point: log in, sit in the lobby, then hand off to the game window.

`python -m client.run <ws_url>` is the whole client-side story in one file: login()
does the shell handshake, run_lobby() blocks until the server seats this connection in
a room, and _build_game_window() wires that room's ServerConnection into a fresh
GameWindow (dispatcher, score/log/sound subscribers, renderer) for the frame loop to
take over.
"""

import os
import sys

import constants
from client.game_window import GameWindow, SnapshotView
from client.home_screen import login, run_lobby
from events.action_history import ActionHistory
from events.dispatcher import EventDispatcher
from events.score_tracker import ScoreTracker
from events.sound_system import SOUND_FILE_BY_EVENT, SoundSystem
from input.controller_builder import build_controller
from logging_setup import configure_logging
from view.game_view import GameView
from view.piece_animations import AnimationLibrary


def _sound_paths():
    return {
        filename: os.path.join(constants.SOUNDS_DIR, filename)
        for filename in set(SOUND_FILE_BY_EVENT.values())
    }


def _build_game_window(connection, snapshot_view, game_snapshot, clock_ms, room_id):
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
        connection, snapshot_view, game_snapshot.board_width, game_snapshot.board_height,
        cell_size=constants.CELL_SIZE, x_offset=constants.PANEL_WIDTH,
    )

    return GameWindow(
        connection, snapshot_view, dispatcher, score_tracker, action_history,
        sound_system, _sound_paths(), view, controller, room_id=room_id,
    )


def run(ws_url):
    connection, username, rating = login(ws_url)
    print(f"Connected as {username} (rating {rating})")

    with connection:
        room_id, role, game_snapshot, clock_ms = run_lobby(connection)
        print(f"Placed in room {room_id} as {role}")

        snapshot_view = SnapshotView()
        game_window = _build_game_window(connection, snapshot_view, game_snapshot, clock_ms, room_id)
        game_window.run()


def main():
    if len(sys.argv) < 2:
        print("usage: python -m client.run <ws_url>")
        sys.exit(1)
    configure_logging(constants.CLIENT_LOG_PATH)
    run(sys.argv[1])


if __name__ == "__main__":
    main()
