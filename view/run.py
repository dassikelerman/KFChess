"""Interactive entry point: opens a window and lets two players (one per
color, sharing one mouse) click pieces to play in real time. Left click
selects/moves (Controller.click); right click jumps (Controller.jump).

Run from the project root with:
    python -m view.run

(Must be run as a module, not `python view/run.py` directly - this file
lives in a subdirectory, so a direct script run would not put the project
root on sys.path and `import app`/`import constants` would fail.)

Reuses app.build_app() for all the existing game-object wiring (engine,
board, board_mapper) instead of re-deriving it, and only adds what a real
interactive session needs on top of that: a second Controller (one per
color - see view/click_router.py for why two, and how a single mouse's
clicks are routed between them) and the render loop (view/game_view.py).
"""

import time

import cv2

import app
import constants
from assets.piece_animations import AnimationLibrary
from input.controller import Controller
from view.click_router import ClickRouter
from view.game_view import GameView

# Standard chess starting position in this project's own board-text format
# (see board_io.board_parser.build_board) - row 0 is white's promotion
# rank (see PAWN_DIRECTION in constants.py), so white's back rank is last.
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
FRAME_POLL_MS = 16  # ~60Hz event/GUI polling; the physics clock uses real elapsed time regardless


def run(board_text=None):
    app_components = app.build_app(STANDARD_START_BOARD if board_text is None else board_text)
    engine = app_components.engine

    controller_white = Controller(engine, app_components.board_mapper)
    controller_black = Controller(engine, app_components.board_mapper)
    router = ClickRouter(
        app_components.board, app_components.board_mapper, controller_white, controller_black
    )

    view = GameView(
        constants.BOARD_IMAGE_PATH,
        constants.CELL_SIZE,
        app_components.board.width,
        app_components.board.height,
        AnimationLibrary(constants.PIECES_DIR),
    )

    cv2.namedWindow(WINDOW_NAME)
    cv2.setMouseCallback(WINDOW_NAME, lambda event, x, y, flags, userdata: _on_mouse(router, event, x, y))

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


def _on_mouse(router, event, x, y):
    if event == cv2.EVENT_LBUTTONDOWN:
        router.click(x, y)
    elif event == cv2.EVENT_RBUTTONDOWN:
        router.jump(x, y)


if __name__ == "__main__":
    run()
