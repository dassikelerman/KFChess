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

# Not part of the presentation's mandated numbers above - our own choice for how long a
# finished game's room stays around after GameOverEvent before GameRoomRegistry tears it
# down itself, instead of waiting on a client to eventually disconnect (see rooms.py).
ROOM_CLOSE_GRACE_SECONDS = 10

# --- Redis room directory (server/room_directory.py) -------------------------------
# room_id is 128 bits (16 random bytes -> 32 hex chars) so the shared Directory can
# allocate it with negligible collision risk at world scale; it is never typed by a
# human, unlike JOIN_CODE_LENGTH below.
ROOM_ID_BYTES = 16
# join_code is only for a private room's creator to read aloud/type to a friend - short,
# and drawn from an alphabet with no visually-confusable characters (no 0/O, 1/I/l).
JOIN_CODE_LENGTH = 6
JOIN_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
# Last-resort backstop on directory:room/directory:user/directory:join entries - set
# once at creation, never refreshed. The real staleness signal is the owning shard's
# heartbeat (below); this TTL only reclaims entries nobody ever looks up again after
# their shard has died.
DIRECTORY_KEY_TTL_SECONDS = 6 * 60 * 60
# Each Game Server process refreshes one directory:shard:{id}:alive key instead of a
# TTL per room/user - O(shards), not O(rooms x users). TTL must comfortably outlast one
# refresh interval so a slow tick doesn't make a live shard look dead.
SHARD_HEARTBEAT_TTL_SECONDS = 30
SHARD_HEARTBEAT_REFRESH_SECONDS = 10
