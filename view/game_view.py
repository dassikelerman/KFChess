import numpy as np

from model.piece import PieceColor
from view.piece_animations import frame_index_for
from view.img import Img
from view.piece_state_machine import PieceStateMachine

REST_OVERLAY_COLOR_BGR = (230, 160, 90)
REST_OVERLAY_ALPHA = 0.55

SELECTION_FRAME_COLOR_BGR = (60, 220, 255)
SELECTION_FRAME_THICKNESS = 4
SELECTION_FRAME_ALPHA = 0.85

PANEL_BACKGROUND_BGR = {PieceColor.BLACK: (30, 30, 30), PieceColor.WHITE: (235, 235, 235)}
PANEL_TEXT_BGR = {PieceColor.BLACK: (255, 255, 255), PieceColor.WHITE: (20, 20, 20)}
PANEL_TEXT_MARGIN = 14
PANEL_LINE_HEIGHT = 24
PANEL_SCORE_FONT_SIZE = 0.7
PANEL_ACTION_FONT_SIZE = 0.42


class GameView:
    def __init__(
        self, board_image_path, cell_size, board_width, board_height, animation_library, panel_width=0,
    ):
        self._cell_size = cell_size
        self._library = animation_library
        self._panel_width = panel_width
        self._board_x_offset = panel_width
        self._board_image = Img().read(
            board_image_path, size=(board_width * cell_size, board_height * cell_size)
        )
        self._board_pixel_width = board_width * cell_size
        self._canvas_width = self._board_pixel_width + 2 * panel_width
        self._canvas_height = board_height * cell_size
        self._sprite_cache = {}
        self._state_machine = PieceStateMachine(animation_library)
        self._known_piece_ids = set()

    def render(self, ui_snapshot):
        canvas = self._blank_canvas()
        self._draw_board(canvas)
        for piece in ui_snapshot.game.pieces:
            self._draw_piece(canvas, piece, ui_snapshot.clock_ms)
        for piece in ui_snapshot.game.pieces:
            self._draw_rest_overlay(canvas, piece)
        self._draw_selection_frame(canvas, ui_snapshot.selected)
        if self._panel_width > 0:
            self._draw_panel(canvas, PieceColor.BLACK, ui_snapshot)
            self._draw_panel(canvas, PieceColor.WHITE, ui_snapshot)
        self._forget_vanished_pieces(ui_snapshot.game)
        return canvas

    def _forget_vanished_pieces(self, snapshot):
        current_ids = {piece.id for piece in snapshot.pieces}
        for piece_id in self._known_piece_ids - current_ids:
            self._state_machine.forget(piece_id)
        self._known_piece_ids = current_ids

    def _blank_canvas(self):
        channels = self._board_image.img.shape[2]
        img = np.zeros((self._canvas_height, self._canvas_width, channels), dtype=self._board_image.img.dtype)
        if self._panel_width > 0:
            img[:, :self._panel_width] = self._panel_fill(PieceColor.BLACK, channels)
            img[:, self._panel_width + self._board_pixel_width:] = self._panel_fill(PieceColor.WHITE, channels)
        canvas = Img()
        canvas.img = img
        return canvas

    def _panel_fill(self, color, channels):
        bgr = PANEL_BACKGROUND_BGR[color]
        return (*bgr, 255) if channels == 4 else bgr

    def _draw_board(self, canvas):
        x0 = self._board_x_offset
        canvas.img[:, x0:x0 + self._board_pixel_width] = self._board_image.img

    def _draw_panel(self, canvas, color, ui_snapshot):
        x0 = 0 if color == PieceColor.BLACK else self._board_x_offset + self._board_pixel_width
        text_color = PANEL_TEXT_BGR[color]
        score = ui_snapshot.score.get(color, 0)

        panel = Img()
        panel.img = canvas.img[:, x0:x0 + self._panel_width].copy()

        y = PANEL_TEXT_MARGIN + PANEL_LINE_HEIGHT
        panel.put_text(f"{color.value.upper()}  Score: {score}", PANEL_TEXT_MARGIN, y, PANEL_SCORE_FONT_SIZE, text_color)

        actions = [a for a in ui_snapshot.recent_actions if a.color in (color, None)]
        for action in actions:
            y += PANEL_LINE_HEIGHT
            if y > self._canvas_height - PANEL_TEXT_MARGIN:
                break
            panel.put_text(action.text, PANEL_TEXT_MARGIN, y, PANEL_ACTION_FONT_SIZE, text_color)

        canvas.img[:, x0:x0 + self._panel_width] = panel.img

    def _draw_rest_overlay(self, canvas, piece):
        if piece.rest_fraction_remaining is None:
            return

        fraction = piece.rest_fraction_remaining
        color = np.array(REST_OVERLAY_COLOR_BGR)
        x = int(piece.col * self._cell_size) + self._board_x_offset
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
        x = int(col * self._cell_size) + self._board_x_offset
        y = int(row * self._cell_size)
        size = self._cell_size
        t = SELECTION_FRAME_THICKNESS

        self._blend(canvas.img[y:y + t, x:x + size, :3], color, SELECTION_FRAME_ALPHA)
        self._blend(canvas.img[y + size - t:y + size, x:x + size, :3], color, SELECTION_FRAME_ALPHA)
        self._blend(canvas.img[y:y + size, x:x + t, :3], color, SELECTION_FRAME_ALPHA)
        self._blend(canvas.img[y:y + size, x + size - t:x + size, :3], color, SELECTION_FRAME_ALPHA)

    def _blend(self, roi, color, alpha):
        roi[:] = (roi * (1 - alpha) + color * alpha).astype(roi.dtype)

    def _draw_piece(self, canvas, piece, clock_ms):
        progress = self._state_machine.state_for(piece, clock_ms)
        clip = self._library.get(piece.color, piece.kind, progress.state)
        sprite_path = clip.sprite_paths[frame_index_for(clip, progress.elapsed_ms)]
        sprite = self._sprite(sprite_path)

        x = int(piece.render_col * self._cell_size) + self._board_x_offset
        y = int(piece.render_row * self._cell_size)
        sprite.draw_on(canvas, x, y)

    def _sprite(self, path):
        cached = self._sprite_cache.get(path)
        if cached is None:
            cached = Img().read(path, size=(self._cell_size, self._cell_size), keep_aspect=True)
            self._sprite_cache[path] = cached
        return cached
