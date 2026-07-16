import os
from types import SimpleNamespace

import numpy as np
import pytest

import constants
from view.piece_animations import AnimationLibrary
from engine.snapshot import PieceSnapshot
from model.piece import PieceColor, PieceKind
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


def make_view(board_width=1, board_height=1):
    return GameView(
        constants.BOARD_IMAGE_PATH, constants.CELL_SIZE, board_width, board_height,
        AnimationLibrary(constants.PIECES_DIR),
    )


def sprite_paths_drawn(view):
    return set(view._sprite_cache.keys())


@requires_real_assets
def test_render_plays_long_rest_between_move_and_idle_instead_of_jumping_straight_to_idle():
    view = make_view()

    view.render(snapshot([piece(is_moving=True, is_jumping=False)]), clock_ms=0)
    assert not any("long_rest" in path for path in sprite_paths_drawn(view))

    # The engine reports idle the instant the piece lands - GameView must
    # hand this off to PieceStateMachine, which plays long_rest before
    # idle, rather than deciding IDLE itself and skipping the rest clip.
    view.render(snapshot([piece(is_moving=False, is_jumping=False)]), clock_ms=10)
    assert any("long_rest" in path for path in sprite_paths_drawn(view))


@requires_real_assets
def test_render_plays_short_rest_between_jump_and_idle_instead_of_jumping_straight_to_idle():
    view = make_view()

    view.render(snapshot([piece(is_moving=False, is_jumping=True)]), clock_ms=0)
    assert not any("short_rest" in path for path in sprite_paths_drawn(view))

    view.render(snapshot([piece(is_moving=False, is_jumping=False)]), clock_ms=10)
    assert any("short_rest" in path for path in sprite_paths_drawn(view))


@requires_real_assets
def test_render_forgets_a_piece_that_disappears_from_the_snapshot():
    view = make_view()

    view.render(snapshot([piece(is_moving=True, is_jumping=False)]), clock_ms=0)
    assert "wq1" in view._animator._entered_at
    assert "wq1" in view._state_machine._entries

    view.render(snapshot([]), clock_ms=10)  # the piece was captured/removed

    assert "wq1" not in view._animator._entered_at
    assert "wq1" not in view._state_machine._entries


# -- selection frame ----------------------------------------------------


@requires_real_assets
def test_render_draws_a_selection_frame_around_the_selected_cell():
    view = make_view(board_width=2, board_height=2)
    original = view._board_image.img.copy()
    cell_size = constants.CELL_SIZE

    frame = view.render(snapshot([]), clock_ms=0, selected=(0, 1))

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

    frame = view.render(snapshot([]), clock_ms=0, selected=None)

    assert np.array_equal(frame.img[:, :, :3], original[:, :, :3])


# -- rest (cooldown) overlay ----------------------------------------------


@requires_real_assets
def test_render_covers_the_top_of_a_resting_piece_by_its_remaining_rest_fraction():
    cell_size = constants.CELL_SIZE

    resting_view = make_view()
    resting = resting_view.render(
        snapshot([piece(is_moving=False, is_jumping=False, rest_fraction_remaining=0.3)]), clock_ms=0
    )

    baseline_view = make_view()
    baseline = baseline_view.render(
        snapshot([piece(is_moving=False, is_jumping=False, rest_fraction_remaining=None)]), clock_ms=0
    )

    covered_row = int(cell_size * 0.3) - 1  # inside the covered top band
    uncovered_row = cell_size - 1  # bottom row, well below the covered band

    assert not np.array_equal(resting.img[covered_row, 0, :3], baseline.img[covered_row, 0, :3])
    assert np.array_equal(resting.img[uncovered_row, 0, :3], baseline.img[uncovered_row, 0, :3])


@requires_real_assets
def test_render_draws_no_rest_overlay_once_rest_fraction_remaining_is_none():
    view = make_view()

    frame = view.render(
        snapshot([piece(is_moving=False, is_jumping=False, rest_fraction_remaining=None)]), clock_ms=0
    )
    baseline_view = make_view()
    baseline = baseline_view.render(
        snapshot([piece(is_moving=False, is_jumping=False, rest_fraction_remaining=None)]), clock_ms=0
    )

    assert np.array_equal(frame.img[:, :, :3], baseline.img[:, :, :3])
