"""Interactive entry point. Left click selects/moves; right click jumps.

Run as a module from the project root: python -m view.run
(A direct `python view/run.py` won't put the project root on sys.path.)
"""

import time

import cv2

import constants
from app.game_builder import build_game
from view.piece_animations import AnimationLibrary
from input.controller_builder import build_controller
from view.game_ui_snapshot import build_ui_snapshot
from view.game_view import GameView


def run(board_text=None):
    game = build_game(constants.STANDARD_START_BOARD if board_text is None else board_text)
    engine = game.engine

    # The GUI's own click-to-cell mapping needs to know about the side
    # panels shifting the board right - text/run.py builds its own
    # controller with zero offsets since it has no panels at all.
    controller = build_controller(
        engine, game.board, cell_size=constants.CELL_SIZE, x_offset=constants.PANEL_WIDTH,
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

        ui_snapshot = build_ui_snapshot(engine, controller, game.score_tracker, game.action_history)
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
