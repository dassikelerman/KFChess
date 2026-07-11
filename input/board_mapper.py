def pixel_to_cell(x, y, board, config):
    row = y // config.CELL_SIZE
    col = x // config.CELL_SIZE
    if not board.in_bounds(row, col):
        return None
    return row, col
