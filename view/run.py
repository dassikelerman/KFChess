"""Interactive entry point. Left click selects/moves; right click jumps.

Run as a module from the project root: python -m view.run
(A direct `python view/run.py` won't put the project root on sys.path.)
"""

import time

import cv2

import constants
from app.game_builder import build_game
from assets.piece_animations import AnimationLibrary
from input.controller import Controller
from view.game_view import GameView

STANDARD_START_BOARD = [
    "bR bN bB bQ bK bB bN bR",
    "bP bP bP bP bP bP bP bP",
    ". . . . . . . .",
    ". . . . . . . .",
    ". . . . . . . .",
    ". . . . . . . .",
    "wP wP wP wP wP wP wP wP",
    "wR wN wB wQ wK wB wN wR",
]

WINDOW_NAME = "KungFu Chess"
ESCAPE_KEY = 27
FRAME_POLL_MS = 16


def run(board_text=None):
    game = build_game(STANDARD_START_BOARD if board_text is None else board_text)
    engine = game.engine

    controller = Controller(engine, game.board_mapper)

    view = GameView(
        constants.BOARD_IMAGE_PATH,
        constants.CELL_SIZE,
        game.board.width,
        game.board.height,
        AnimationLibrary(constants.PIECES_DIR),
    )

    cv2.namedWindow(WINDOW_NAME)
    cv2.setMouseCallback(WINDOW_NAME, lambda event, x, y, flags, userdata: _on_mouse(controller, event, x, y))

    last_tick = time.perf_counter()
    while True:
        now = time.perf_counter()
        dt_ms = round((now - last_tick) * 1000)
        last_tick = now
        engine.wait(dt_ms)

        frame = view.render(engine.snapshot(), engine.clock)
        cv2.imshow(WINDOW_NAME, frame.img)

        key = cv2.waitKey(FRAME_POLL_MS) & 0xFF
        if key == ESCAPE_KEY or cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
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
