import os
import time
import winsound

import cv2

import constants
from app.game_builder import build_game
from events.action_history import ActionHistory
from events.score_tracker import ScoreTracker
from events.sound_system import SOUND_FILE_BY_EVENT, SoundSystem
from view.piece_animations import AnimationLibrary
from input.controller_builder import build_controller
from view.game_ui_snapshot import build_ui_snapshot
from view.game_view import GameView


def _sound_paths():
    return {
        filename: os.path.join(constants.SOUNDS_DIR, filename)
        for filename in set(SOUND_FILE_BY_EVENT.values())
    }


def run(board_text=None):
    game = build_game(constants.STANDARD_START_BOARD if board_text is None else board_text)
    engine = game.engine
    score_tracker = ScoreTracker(game.dispatcher)
    action_history = ActionHistory(game.dispatcher)
    sound_system = SoundSystem(game.dispatcher)
    sound_paths = _sound_paths()

    controller = build_controller(
        engine, engine, game.board.width, game.board.height,
        cell_size=constants.CELL_SIZE, x_offset=constants.PANEL_WIDTH,
    )

    view = GameView(
        constants.BOARD_IMAGE_PATH,
        constants.CELL_SIZE,
        game.board.width,
        game.board.height,
        AnimationLibrary(constants.PIECES_DIR),
        panel_width=constants.PANEL_WIDTH,
    )

    cv2.namedWindow(constants.WINDOW_NAME)
    cv2.setMouseCallback(
        constants.WINDOW_NAME, lambda event, x, y, flags, userdata: _on_mouse(controller, event, x, y)
    )

    last_tick = time.perf_counter()
    while True:
        now = time.perf_counter()
        dt_ms = round((now - last_tick) * 1000)
        last_tick = now
        engine.wait(dt_ms)
        controller.refresh_selection()

        for filename in sound_system.drain_pending():
            winsound.PlaySound(sound_paths[filename], winsound.SND_FILENAME | winsound.SND_ASYNC)

        ui_snapshot = build_ui_snapshot(engine, controller, score_tracker, action_history)
        frame = view.render(ui_snapshot)
        frame.show(constants.WINDOW_NAME)

        key = cv2.waitKey(constants.FRAME_POLL_MS) & 0xFF
        if key == constants.ESCAPE_KEY or cv2.getWindowProperty(constants.WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
            break
        if engine.game_over:
            cv2.waitKey(0)
            break

    cv2.destroyAllWindows()


def _on_mouse(controller, event, x, y):
    if event == cv2.EVENT_LBUTTONDOWN:
        controller.click(x, y)
    elif event == cv2.EVENT_RBUTTONDOWN:
        controller.jump(x, y)


if __name__ == "__main__":
    run()
