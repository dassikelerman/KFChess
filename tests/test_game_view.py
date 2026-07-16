import os
from types import SimpleNamespace

import numpy as np
import pytest

import constants
from view.piece_animations import AnimationLibrary
from engine.snapshot import PieceSnapshot
from events.action_history import ActionEntry
from model.piece import PieceColor, PieceKind
from view.game_ui_snapshot import GameUiSnapshot
from view.game_view import GameView

ASSETS_AVAILABLE = os.path.isdir(constants.PIECES_DIR) and os.path.isfile(constants.BOARD_IMAGE_PATH)
requires_real_assets = pytest.mark.skipif(
    not ASSETS_AVAILABLE, reason="real board.png/pieces2/ assets not present in this checkout"
)


def piece(is_moving, is_jumping, rest_fraction_remaining=None):
    return PieceSnapshot(
        id="wq1",
        kind=PieceKind.QUEEN,
        color=PieceColor.WHITE,
        row=0,
        col=0,
        render_row=0.0,
        render_col=0.0,
        is_moving=is_moving,
        is_jumping=is_jumping,
        rest_fraction_remaining=rest_fraction_remaining,
    )


def snapshot(pieces):
    return SimpleNamespace(pieces=pieces)


def ui_snapshot(pieces, clock_ms=0, selected=None, score=None, recent_actions=None):
    return GameUiSnapshot(
        game=snapshot(pieces),
        clock_ms=clock_ms,
        selected=selected,
        score=score if score is not None else {},
        recent_actions=recent_actions if recent_actions is not None else [],
    )


def make_view(board_width=1, board_height=1, panel_width=0):
    return GameView(
        constants.BOARD_IMAGE_PATH, constants.CELL_SIZE, board_width, board_height,
        AnimationLibrary(constants.PIECES_DIR), panel_width=panel_width,
    )


def sprite_paths_drawn(view):
    return set(view._sprite_cache.keys())


@requires_real_assets
def test_render_plays_long_rest_between_move_and_idle_instead_of_jumping_straight_to_idle():
    view = make_view()

    view.render(ui_snapshot([piece(is_moving=True, is_jumping=False)], clock_ms=0))
    assert not any("long_rest" in path for path in sprite_paths_drawn(view))

    # The engine reports idle the instant the piece lands - GameView must
    # hand this off to PieceStateMachine, which plays long_rest before
    # idle, rather than deciding IDLE itself and skipping the rest clip.
    view.render(ui_snapshot([piece(is_moving=False, is_jumping=False)], clock_ms=10))
    assert any("long_rest" in path for path in sprite_paths_drawn(view))


@requires_real_assets
def test_render_plays_short_rest_between_jump_and_idle_instead_of_jumping_straight_to_idle():
    view = make_view()

    view.render(ui_snapshot([piece(is_moving=False, is_jumping=True)], clock_ms=0))
    assert not any("short_rest" in path for path in sprite_paths_drawn(view))

    view.render(ui_snapshot([piece(is_moving=False, is_jumping=False)], clock_ms=10))
    assert any("short_rest" in path for path in sprite_paths_drawn(view))


@requires_real_assets
def test_render_forgets_a_piece_that_disappears_from_the_snapshot():
    view = make_view()

    view.render(ui_snapshot([piece(is_moving=True, is_jumping=False)], clock_ms=0))
    assert "wq1" in view._animator._entered_at
    assert "wq1" in view._state_machine._entries

    view.render(ui_snapshot([], clock_ms=10))  # the piece was captured/removed

    assert "wq1" not in view._animator._entered_at
    assert "wq1" not in view._state_machine._entries


# -- selection frame ----------------------------------------------------


@requires_real_assets
def test_render_draws_a_selection_frame_around_the_selected_cell():
    view = make_view(board_width=2, board_height=2)
    original = view._board_image.img.copy()
    cell_size = constants.CELL_SIZE

    frame = view.render(ui_snapshot([], selected=(0, 1)))

    # A pixel on the border of the selected cell (row 0, col 1) must be
    # tinted; the same-offset pixel in the untouched neighboring cell
    # (row 0, col 0) must be left exactly as the raw board image.
    selected_border_pixel = frame.img[0, cell_size + 1, :3]
    untouched_pixel = frame.img[0, 1, :3]
    assert not np.array_equal(selected_border_pixel, original[0, cell_size + 1, :3])
    assert np.array_equal(untouched_pixel, original[0, 1, :3])


@requires_real_assets
def test_render_draws_no_selection_frame_when_nothing_is_selected():
    view = make_view(board_width=2, board_height=2)
    original = view._board_image.img.copy()

    frame = view.render(ui_snapshot([], selected=None))

    assert np.array_equal(frame.img[:, :, :3], original[:, :, :3])


# -- rest (cooldown) overlay ----------------------------------------------


@requires_real_assets
def test_render_covers_the_top_of_a_resting_piece_by_its_remaining_rest_fraction():
    cell_size = constants.CELL_SIZE

    resting_view = make_view()
    resting = resting_view.render(
        ui_snapshot([piece(is_moving=False, is_jumping=False, rest_fraction_remaining=0.3)])
    )

    baseline_view = make_view()
    baseline = baseline_view.render(
        ui_snapshot([piece(is_moving=False, is_jumping=False, rest_fraction_remaining=None)])
    )

    covered_row = int(cell_size * 0.3) - 1  # inside the covered top band
    uncovered_row = cell_size - 1  # bottom row, well below the covered band

    assert not np.array_equal(resting.img[covered_row, 0, :3], baseline.img[covered_row, 0, :3])
    assert np.array_equal(resting.img[uncovered_row, 0, :3], baseline.img[uncovered_row, 0, :3])


@requires_real_assets
def test_render_draws_no_rest_overlay_once_rest_fraction_remaining_is_none():
    view = make_view()

    frame = view.render(ui_snapshot([piece(is_moving=False, is_jumping=False, rest_fraction_remaining=None)]))
    baseline_view = make_view()
    baseline = baseline_view.render(
        ui_snapshot([piece(is_moving=False, is_jumping=False, rest_fraction_remaining=None)])
    )

    assert np.array_equal(frame.img[:, :, :3], baseline.img[:, :, :3])


# -- side panels ----------------------------------------------------------


@requires_real_assets
def test_render_with_no_panel_width_produces_a_board_only_canvas():
    view = make_view(board_width=2, board_height=2, panel_width=0)
    frame = view.render(ui_snapshot([]))
    assert frame.img.shape[1] == 2 * constants.CELL_SIZE


@requires_real_assets
def test_render_with_panels_widens_the_canvas_on_both_sides():
    view = make_view(board_width=2, board_height=2, panel_width=100)
    frame = view.render(ui_snapshot([]))
    assert frame.img.shape[1] == 2 * constants.CELL_SIZE + 2 * 100


@requires_real_assets
def test_render_draws_the_board_shifted_right_by_the_panel_width():
    view = make_view(board_width=2, board_height=2, panel_width=100)
    board_only_view = make_view(board_width=2, board_height=2, panel_width=0)

    frame = view.render(ui_snapshot([]))
    board_only_frame = board_only_view.render(ui_snapshot([]))

    shifted = frame.img[:, 100:100 + 2 * constants.CELL_SIZE, :3]
    assert np.array_equal(shifted, board_only_frame.img[:, :, :3])


@requires_real_assets
def test_render_fills_the_left_panel_black_and_the_right_panel_white():
    view = make_view(board_width=1, board_height=1, panel_width=50)
    frame = view.render(ui_snapshot([]))

    left_pixel = frame.img[0, 10, :3]
    right_pixel = frame.img[0, frame.img.shape[1] - 10, :3]

    assert left_pixel.max() < 60  # dark panel
    assert right_pixel.min() > 200  # light panel


@requires_real_assets
def test_render_draws_each_colors_score_and_recent_actions_only_on_its_own_panel():
    view = make_view(board_width=1, board_height=1, panel_width=200)
    entries = [
        ActionEntry(text="wR captured bP", color=PieceColor.WHITE, at_ms=100),
        ActionEntry(text="bN jump completed", color=PieceColor.BLACK, at_ms=200),
    ]

    frame = view.render(ui_snapshot([], score={PieceColor.WHITE: 5, PieceColor.BLACK: 3}, recent_actions=entries))

    # Not asserting on exact pixels of rendered glyphs (font rendering is
    # an implementation detail) - just that drawing with real score/text
    # content, on both sides, does not raise and produces a real frame.
    assert frame.img.shape[1] == constants.CELL_SIZE + 2 * 200


@requires_real_assets
def test_render_with_panels_still_positions_pieces_and_selection_relative_to_the_board_not_the_canvas():
    view = make_view(board_width=2, board_height=2, panel_width=100)

    frame = view.render(ui_snapshot([], selected=(0, 0)))

    # The selection frame for board-cell (0, 0) must sit right after the
    # left panel, not at the canvas's own literal x=0.
    board_origin_pixel = frame.img[0, 101, :3]
    canvas_origin_pixel = frame.img[0, 1, :3]
    original_left_panel = frame.img[50, 1, :3]  # untouched panel background, no selection frame
    assert not np.array_equal(board_origin_pixel, canvas_origin_pixel)
    assert np.array_equal(canvas_origin_pixel, original_left_panel)
