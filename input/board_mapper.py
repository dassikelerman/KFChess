from model.position import Position


class BoardMapper:
    """Converts pixel coordinates into board cells - the one piece of the
    click-handling pipeline that knows pixels exist at all.
    """

    def __init__(self, cell_size, board_width, board_height):
        self._cell_size = cell_size
        self._board_width = board_width
        self._board_height = board_height

    def pixel_to_cell(self, x, y):
        row = y // self._cell_size
        col = x // self._cell_size
        if not (0 <= row < self._board_height and 0 <= col < self._board_width):
            return None
        return Position(row, col)
