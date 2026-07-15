from assets.piece_animations import frame_index_for
from view.img import Img
from view.piece_animator import PieceAnimator


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
        return canvas

    def _draw_piece(self, canvas, piece, clock_ms):
        clip = self._library.get(piece.color, piece.kind, piece.animation_state)
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
