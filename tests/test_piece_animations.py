import os

import pytest

import constants
from assets.piece_animations import AnimationLibrary, frame_index_for, token_to_folder
from model.piece import AnimationState, PieceColor, PieceKind

PIECES_DIR_EXISTS = os.path.isdir(constants.PIECES_DIR)
requires_pieces_dir = pytest.mark.skipif(
    not PIECES_DIR_EXISTS, reason=f"{constants.PIECES_DIR}/ asset tree not present in this checkout"
)


def test_token_to_folder_covers_all_12_combinations():
    expected = {
        (PieceColor.WHITE, PieceKind.KING): "KW",
        (PieceColor.BLACK, PieceKind.KING): "KB",
        (PieceColor.WHITE, PieceKind.QUEEN): "QW",
        (PieceColor.BLACK, PieceKind.QUEEN): "QB",
        (PieceColor.WHITE, PieceKind.ROOK): "RW",
        (PieceColor.BLACK, PieceKind.ROOK): "RB",
        (PieceColor.WHITE, PieceKind.BISHOP): "BW",
        (PieceColor.BLACK, PieceKind.BISHOP): "BB",
        (PieceColor.WHITE, PieceKind.KNIGHT): "NW",
        (PieceColor.BLACK, PieceKind.KNIGHT): "NB",
        (PieceColor.WHITE, PieceKind.PAWN): "PW",
        (PieceColor.BLACK, PieceKind.PAWN): "PB",
    }
    for (color, kind), folder in expected.items():
        assert token_to_folder(color, kind) == folder


def test_token_to_folder_produces_exactly_the_pieces2_directory_names():
    computed = {token_to_folder(color, kind) for color in PieceColor for kind in PieceKind}
    assert computed == {
        "BB", "BW", "KB", "KW", "NB", "NW", "PB", "PW", "QB", "QW", "RB", "RW",
    }


class _FakeClip:
    def __init__(self, frame_count, frames_per_sec, is_loop):
        self.sprite_paths = [f"{i}.png" for i in range(frame_count)]
        self.config = _FakeConfig(frames_per_sec, is_loop)


class _FakeConfig:
    def __init__(self, frames_per_sec, is_loop):
        self.frames_per_sec = frames_per_sec
        self.is_loop = is_loop


def test_frame_index_for_at_elapsed_zero_is_the_first_frame():
    clip = _FakeClip(frame_count=5, frames_per_sec=10, is_loop=True)
    assert frame_index_for(clip, elapsed_ms=0) == 0


def test_frame_index_for_mid_animation():
    # 10 fps -> 100ms per frame; 250ms in is frame index 2
    clip = _FakeClip(frame_count=5, frames_per_sec=10, is_loop=True)
    assert frame_index_for(clip, elapsed_ms=250) == 2


def test_frame_index_for_wraps_when_looping():
    # 5 frames at 10fps = 500ms per cycle; 700ms in wraps to frame 2
    clip = _FakeClip(frame_count=5, frames_per_sec=10, is_loop=True)
    assert frame_index_for(clip, elapsed_ms=700) == 2


def test_frame_index_for_clamps_to_last_frame_when_not_looping():
    clip = _FakeClip(frame_count=5, frames_per_sec=10, is_loop=False)
    assert frame_index_for(clip, elapsed_ms=10_000) == 4  # way past the end, stays on last frame


def test_frame_index_for_non_looping_mid_animation_does_not_clamp_early():
    clip = _FakeClip(frame_count=5, frames_per_sec=10, is_loop=False)
    assert frame_index_for(clip, elapsed_ms=250) == 2


@requires_pieces_dir
def test_animation_library_loads_the_move_clip_matching_its_config_json():
    library = AnimationLibrary(constants.PIECES_DIR)
    clip = library.get(PieceColor.WHITE, PieceKind.QUEEN, AnimationState.MOVE)

    assert clip.config.speed_m_per_sec == 1.5
    assert clip.config.next_state_when_finished == "long_rest"
    assert clip.config.frames_per_sec == 12
    assert clip.config.is_loop is True
    assert len(clip.sprite_paths) == 5


@requires_pieces_dir
def test_animation_library_covers_every_token_and_state():
    library = AnimationLibrary(constants.PIECES_DIR)
    for color in PieceColor:
        for kind in PieceKind:
            for state in AnimationState:
                clip = library.get(color, kind, state)
                assert len(clip.sprite_paths) == 5
