"""Reads the pieces2/ asset tree into in-memory animation metadata.

Deliberately has no dependency on cv2/pygame - only pathlib/json/
dataclasses - so it can be unit tested without a display. Actually loading
sprite pixels into memory is the renderer's job (view/), not this module's;
AnimationClip only carries file paths.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from model.piece import AnimationState, PieceColor, PieceKind


def token_to_folder(color: PieceColor, kind: PieceKind) -> str:
    """Maps the engine's internal piece identity to its pieces2/ asset
    folder name, e.g. (PieceColor.WHITE, PieceKind.QUEEN) -> "QW".

    This is *not* the same as the engine's own board token (model.piece.
    kind_letter/_token elsewhere use lowercase color + uppercase kind,
    e.g. "wQ") - pieces2 folders are <KIND><COLOR>, both uppercase.
    """
    return kind.value + color.value.upper()


@dataclass(frozen=True)
class AnimationConfig:
    speed_m_per_sec: float
    next_state_when_finished: str
    frames_per_sec: int
    is_loop: bool

    @staticmethod
    def from_json(data: dict) -> "AnimationConfig":
        return AnimationConfig(
            speed_m_per_sec=data["physics"]["speed_m_per_sec"],
            next_state_when_finished=data["physics"]["next_state_when_finished"],
            frames_per_sec=data["graphics"]["frames_per_sec"],
            is_loop=data["graphics"]["is_loop"],
        )


@dataclass(frozen=True)
class AnimationClip:
    config: AnimationConfig
    sprite_paths: list  # list[str] - loading pixels is the renderer's job


class AnimationLibrary:
    """Scans pieces_dir once (at construction) and exposes AnimationClip
    lookup by (color, kind, state)."""

    def __init__(self, pieces_dir):
        self._clips = self._scan(Path(pieces_dir))

    def get(self, color: PieceColor, kind: PieceKind, state: AnimationState) -> AnimationClip:
        return self._clips[(token_to_folder(color, kind), state)]

    def _scan(self, pieces_dir):
        clips = {}
        for color in PieceColor:
            for kind in PieceKind:
                folder = token_to_folder(color, kind)
                for state in AnimationState:
                    clips[(folder, state)] = self._load_clip(pieces_dir / folder / "states" / state.value)
        return clips

    def _load_clip(self, state_dir):
        config_data = json.loads((state_dir / "config.json").read_text())
        sprite_paths = sorted(
            (str(path) for path in (state_dir / "sprites").glob("*.png")),
            key=lambda path: int(Path(path).stem),
        )
        return AnimationClip(config=AnimationConfig.from_json(config_data), sprite_paths=sprite_paths)


def frame_index_for(clip: AnimationClip, elapsed_ms: float) -> int:
    frame_count = len(clip.sprite_paths)
    frame = int(elapsed_ms / 1000 * clip.config.frames_per_sec)
    if clip.config.is_loop:
        return frame % frame_count
    return min(frame, frame_count - 1)
