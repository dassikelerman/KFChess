import numpy as np

from assets.piece_animations import frame_index_for
from view.img import Img
from view.piece_animator import PieceAnimator
from view.piece_state_machine import PieceStateMachine

# Height is normalized against each rest's own duration (see
# RealTimeArbiter.rest_remaining_fraction), so the curtain covering the
# piece shrinks from the top down at a pace matching that rest's own
# length, with no separate speed setting needed.
REST_OVERLAY_COLOR_BGR = (230, 160, 90)
REST_OVERLAY_ALPHA = 0.55

SELECTION_FRAME_COLOR_BGR = (60, 220, 255)
SELECTION_FRAME_THICKNESS = 4
SELECTION_FRAME_ALPHA = 0.85


class GameView:
    def __init__(self, board_image_path, cell_size, board_width, board_height, animation_library):
        self._cell_size = cell_size
        self._library = animation_library
        self._board_image = Img().read(
            board_image_path, size=(board_width * cell_size, board_height * cell_size)
        )
        self._sprite_cache = {}
        self._animator = PieceAnimator()
        self._state_machine = PieceStateMachine(animation_library)
        self._known_piece_ids = set()

    def render(self, snapshot, clock_ms, selected=None):
        canvas = Img()
        canvas.img = self._board_image.img.copy()
        for piece in snapshot.pieces:
            self._draw_piece(canvas, piece, clock_ms)
        # Own pass after every piece, so the tint sits on top of the
        # sprite instead of being hidden underneath it.
        for piece in snapshot.pieces:
            self._draw_rest_overlay(canvas, piece)
        # Drawn last so the selection frame is never hidden under a
        # piece or its rest overlay. `selected` is owned by Controller
        # and handed to GameView purely for drawing - it is not part of
        # GameSnapshot or GameEngine state.
        self._draw_selection_frame(canvas, selected)
        self._forget_vanished_pieces(snapshot)
        return canvas

    def _forget_vanished_pieces(self, snapshot):
        current_ids = {piece.id for piece in snapshot.pieces}
        for piece_id in self._known_piece_ids - current_ids:
            self._animator.forget(piece_id)
            self._state_machine.forget(piece_id)
        self._known_piece_ids = current_ids

    def _draw_rest_overlay(self, canvas, piece):
        if piece.rest_fraction_remaining is None:
            return

        fraction = piece.rest_fraction_remaining
        color = np.array(REST_OVERLAY_COLOR_BGR)
        x = int(piece.col * self._cell_size)
        y = int(piece.row * self._cell_size)
        size = self._cell_size

        height = int(size * fraction)
        if height <= 0:
            return
        self._blend(canvas.img[y:y + height, x:x + size, :3], color, REST_OVERLAY_ALPHA)

    def _draw_selection_frame(self, canvas, selected):
        if selected is None:
            return

        row, col = selected
        color = np.array(SELECTION_FRAME_COLOR_BGR)
        x = int(col * self._cell_size)
        y = int(row * self._cell_size)
        size = self._cell_size
        t = SELECTION_FRAME_THICKNESS

        self._blend(canvas.img[y:y + t, x:x + size, :3], color, SELECTION_FRAME_ALPHA)  # top
        self._blend(canvas.img[y + size - t:y + size, x:x + size, :3], color, SELECTION_FRAME_ALPHA)  # bottom
        self._blend(canvas.img[y:y + size, x:x + t, :3], color, SELECTION_FRAME_ALPHA)  # left
        self._blend(canvas.img[y:y + size, x + size - t:x + size, :3], color, SELECTION_FRAME_ALPHA)  # right

    def _blend(self, roi, color, alpha):
        roi[:] = (roi * (1 - alpha) + color * alpha).astype(roi.dtype)

    def _draw_piece(self, canvas, piece, clock_ms):
        state = self._state_machine.state_for(piece, clock_ms)
        clip = self._library.get(piece.color, piece.kind, state)
        elapsed_ms = self._animator.elapsed_ms_for(piece.id, state, clock_ms)
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
