from model.piece import PieceColor

CELL_SIZE = 100
MOVE_DURATION = 1000
JUMP_DURATION = 1000
LONG_REST_DURATION = 1500  # cooldown after a move lands - see GameEngine's rest handling
SHORT_REST_DURATION = 500  # cooldown after a jump's guard window ends
COLORS = tuple(c.value for c in PieceColor)
PAWN_DIRECTION = {"w": -1, "b": 1}
EMPTY_CELL = "."
BOARD_IMAGE_PATH = "board.png"
PIECES_DIR = "pieces2"
