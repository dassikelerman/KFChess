import os
from types import SimpleNamespace

import pytest

import constants
from assets.piece_animations import AnimationLibrary
from model.game_state import PieceSnapshot
from model.piece import PieceColor, PieceKind
from view.game_view import GameView

ASSETS_AVAILABLE = os.path.isdir(constants.PIECES_DIR) and os.path.isfile(constants.BOARD_IMAGE_PATH)
requires_real_assets = pytest.mark.skipif(
    not ASSETS_AVAILABLE, reason="real board.png/pieces2/ assets not present in this checkout"
)


def piece(is_moving, is_jumping):
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
        rest_fraction_remaining=None,
    )


def snapshot(pieces):
    return SimpleNamespace(pieces=pieces)


def make_view():
    return GameView(
        constants.BOARD_IMAGE_PATH, constants.CELL_SIZE, 1, 1, AnimationLibrary(constants.PIECES_DIR)
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
