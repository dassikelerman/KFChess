from model.position import Position


class BoardMapper:
    """The one piece of the click-handling pipeline that knows pixels
    exist at all - converts them into board cells."""

    def __init__(self, cell_size, board_width, board_height, x_offset=0, y_offset=0):
        self._cell_size = cell_size
        self._board_width = board_width
        self._board_height = board_height
        self._x_offset = x_offset
        self._y_offset = y_offset

    def pixel_to_cell(self, x, y):
        row = (y - self._y_offset) // self._cell_size
        col = (x - self._x_offset) // self._cell_size
        if not (0 <= row < self._board_height and 0 <= col < self._board_width):
            return None
        return Position(row, col)
