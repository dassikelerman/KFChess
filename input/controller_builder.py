from input.board_mapper import BoardMapper
from input.controller import Controller


def build_controller(engine, board, *, cell_size, x_offset=0, y_offset=0):
    board_mapper = BoardMapper(
        cell_size=cell_size, board_width=board.width, board_height=board.height,
        x_offset=x_offset, y_offset=y_offset,
    )
    return Controller(action_sink=engine, state_reader=engine, board_mapper=board_mapper)
