from model.piece import PieceColor

CELL_SIZE = 100
MOVE_DURATION = 1000
JUMP_DURATION = 1000
LONG_REST_DURATION = 1500
SHORT_REST_DURATION = 500
COLORS = tuple(c.value for c in PieceColor)
PAWN_DIRECTION = {"w": -1, "b": 1}
EMPTY_CELL = "."
BOARD_IMAGE_PATH = "board.png"
PIECES_DIR = "pieces2"
SOUNDS_DIR = "sounds"
PANEL_WIDTH = 220

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
