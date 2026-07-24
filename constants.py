from model.piece import PieceColor

CELL_SIZE = 100
MOVE_DURATION = 1000
JUMP_DURATION = 1000
LONG_REST_DURATION = 1500
SHORT_REST_DURATION = 500
COLORS = tuple(c.value for c in PieceColor)
PAWN_DIRECTION = {"w": -1, "b": 1}
EMPTY_CELL = "."
BOARD_IMAGE_PATH = "assets/board.png"
PIECES_DIR = "assets/pieces2"
SOUNDS_DIR = "assets/sounds"
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

# Where each side's activity log is written (git-ignored; recreated on every run).
SERVER_LOG_PATH = "server.log"
CLIENT_LOG_PATH = "client.log"

# --- Multiplayer rules (numbers the course presentation specifies) ------------
# Grouped here rather than beside each one's single caller: these five numbers are
# exactly what the presentation's slides mandate, so a reader auditing "does this match
# the spec" should find all of them in one place. Two of them used to be independent
# literals duplicated across files with nothing tying them together - STARTING_RATING
# was hardcoded in both user_store.py's and rating.py's CREATE TABLE, and
# MATCHMAKING_TIMEOUT_SECONDS was matchmaker.py's default *and* a separately hardcoded
# override in ws_server.py - so editing one copy silently could have drifted from the
# other. A single constant closes that gap for good.
STARTING_RATING = 1200               # every new account starts here
RATING_K_FACTOR = 32                 # ELO K-factor: the most one game can move a rating
MATCHMAKING_RATING_TOLERANCE = 100   # "Play" pairs seekers only within +/-100 rating
MATCHMAKING_TIMEOUT_SECONDS = 60     # a lone seeker waits this long before giving up
DISCONNECT_COUNTDOWN_SECONDS = 20    # a dropped player auto-resigns after this long
