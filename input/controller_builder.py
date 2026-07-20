from input.board_mapper import BoardMapper
from input.controller import Controller


def build_controller(action_sink, state_reader, board_width, board_height, *, cell_size, x_offset=0, y_offset=0):
    board_mapper = BoardMapper(
        cell_size=cell_size, board_width=board_width, board_height=board_height,
        x_offset=x_offset, y_offset=y_offset,
    )
    return Controller(action_sink=action_sink, state_reader=state_reader, board_mapper=board_mapper)
