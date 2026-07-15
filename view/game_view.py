import numpy as np

from assets.piece_animations import frame_index_for
from view.animation_state import derive_animation_state
from view.img import Img
from view.piece_animator import PieceAnimator

# A cooldown tint covering a resting piece's whole cell, edge to edge -
# drawn *on top of* the piece itself (not hidden underneath it) so it's
# clearly visible, plus a stronger border so the cell's boundary reads
# unmistakably even where the fill blends into the board's own color.
# Full strength the instant a rest starts, fading linearly to nothing by
# the time PieceSnapshot.rest_fraction_remaining reaches 0. A short rest
# fades out quickly, a long rest slowly, purely because that fraction is
# already normalized against each rest's own actual duration (see
# RealTimeArbiter.rest_remaining_fraction) - no separate speed setting
# needed here.
REST_OVERLAY_COLOR_BGR = (230, 160, 90)
REST_OVERLAY_FILL_MAX_ALPHA = 0.55
REST_OVERLAY_BORDER_MAX_ALPHA = 0.9
REST_OVERLAY_BORDER_THICKNESS = 6


class GameView:
    """Renders a GameSnapshot onto a fresh copy of the board image each
    frame - the board picture and every sprite frame are loaded once and
    cached, since render() runs every frame in the game loop.
    """

    def __init__(self, board_image_path, cell_size, board_width, board_height, animation_library):
        self._cell_size = cell_size
        self._library = animation_library
        self._board_image = Img().read(
            board_image_path, size=(board_width * cell_size, board_height * cell_size)
        )
        self._sprite_cache = {}
        self._animator = PieceAnimator()

    def render(self, snapshot, clock_ms):
        canvas = Img()
        canvas.img = self._board_image.img.copy()
        for piece in snapshot.pieces:
            self._draw_piece(canvas, piece, clock_ms)
        # Drawn as its own pass, after every piece, so the tint sits on
        # top of the sprite instead of being hidden underneath it.
        for piece in snapshot.pieces:
            self._draw_rest_overlay(canvas, piece)
        return canvas

    def _draw_rest_overlay(self, canvas, piece):
        if piece.rest_fraction_remaining is None:
            return

        fraction = piece.rest_fraction_remaining
        color = np.array(REST_OVERLAY_COLOR_BGR)
        x = int(piece.col * self._cell_size)
        y = int(piece.row * self._cell_size)
        size = self._cell_size

        fill_alpha = REST_OVERLAY_FILL_MAX_ALPHA * fraction
        self._blend(canvas.img[y:y + size, x:x + size, :3], color, fill_alpha)

        border_alpha = REST_OVERLAY_BORDER_MAX_ALPHA * fraction
        t = REST_OVERLAY_BORDER_THICKNESS
        self._blend(canvas.img[y:y + t, x:x + size, :3], color, border_alpha)  # top
        self._blend(canvas.img[y + size - t:y + size, x:x + size, :3], color, border_alpha)  # bottom
        self._blend(canvas.img[y:y + size, x:x + t, :3], color, border_alpha)  # left
        self._blend(canvas.img[y:y + size, x + size - t:x + size, :3], color, border_alpha)  # right

    def _blend(self, roi, color, alpha):
        roi[:] = (roi * (1 - alpha) + color * alpha).astype(roi.dtype)

    def _draw_piece(self, canvas, piece, clock_ms):
        clip = self._library.get(piece.color, piece.kind, derive_animation_state(piece))
        elapsed_ms = self._animator.elapsed_ms_for(piece, clock_ms)
        sprite_path = clip.sprite_paths[frame_index_for(clip, elapsed_ms)]
        sprite = self._sprite(sprite_path)

        x = int(piece.render_col * self._cell_size)
        y = int(piece.render_row * self._cell_size)
        sprite.draw_on(canvas, x, y)

    def _sprite(self, path):
        cached = self._sprite_cache.get(path)
        if cached is None:
            cached = Img().read(path, size=(self._cell_size, self._cell_size), keep_aspect=True)
            self._sprite_cache[path] = cached
        return cached
