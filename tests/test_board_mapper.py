from input.board_mapper import BoardMapper
from model.position import Position

CELL_SIZE = 100


def test_pixel_to_cell_maps_a_click_to_its_board_cell():
    mapper = BoardMapper(CELL_SIZE, board_width=3, board_height=3)
    assert mapper.pixel_to_cell(150, 250) == Position(2, 1)


def test_pixel_to_cell_returns_none_outside_the_board_bounds():
    mapper = BoardMapper(CELL_SIZE, board_width=2, board_height=2)
    assert mapper.pixel_to_cell(250, 50) is None  # past the right edge
    assert mapper.pixel_to_cell(50, 250) is None  # past the bottom edge


def test_x_offset_defaults_to_zero_and_does_not_change_existing_behavior():
    mapper = BoardMapper(CELL_SIZE, board_width=3, board_height=3)
    assert mapper.pixel_to_cell(0, 0) == Position(0, 0)


def test_x_offset_shifts_the_board_right_without_changing_cell_size():
    mapper = BoardMapper(CELL_SIZE, board_width=3, board_height=3, x_offset=220)
    # A click at raw pixel x=220 lands on the board's own local x=0.
    assert mapper.pixel_to_cell(220, 0) == Position(0, 0)
    assert mapper.pixel_to_cell(220 + 150, 250) == Position(2, 1)


def test_a_click_inside_the_left_panel_maps_to_no_cell():
    mapper = BoardMapper(CELL_SIZE, board_width=3, board_height=3, x_offset=220)
    assert mapper.pixel_to_cell(50, 50) is None  # inside the panel, left of the board


def test_a_click_past_the_boards_right_edge_with_an_offset_still_maps_to_no_cell():
    mapper = BoardMapper(CELL_SIZE, board_width=2, board_height=2, x_offset=220)
    assert mapper.pixel_to_cell(220 + 250, 50) is None


def test_y_offset_shifts_the_board_down_without_changing_cell_size():
    mapper = BoardMapper(CELL_SIZE, board_width=2, board_height=2, y_offset=50)
    assert mapper.pixel_to_cell(50, 50) == Position(0, 0)
    assert mapper.pixel_to_cell(50, 0) is None  # above the board once shifted down
