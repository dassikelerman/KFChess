from model.piece import PieceColor


class ClickRouter:
    """Routes a raw pixel click to one of two Controllers (one per
    color), without adding color-awareness to Controller itself. The
    color under the first click of a select-then-act gesture owns every
    click in that gesture until its Controller's own selection clears
    (see docs for the full protocol)."""

    def __init__(self, game_engine, board_mapper, controller_white, controller_black):
        self._game_engine = game_engine
        self._board_mapper = board_mapper
        self._controllers = {
            PieceColor.WHITE: controller_white,
            PieceColor.BLACK: controller_black,
        }
        self._active = None

    def click(self, x, y):
        controller = self._active if self._active is not None else self._controller_for(x, y)
        if controller is None:
            return

        controller.click(x, y)
        self._active = controller if controller.selected is not None else None

    def jump(self, x, y):
        controller = self._controller_for(x, y)
        if controller is None:
            return

        controller.jump(x, y)
        if self._active is controller:
            self._active = None

    def _controller_for(self, x, y):
        pos = self._board_mapper.pixel_to_cell(x, y)
        if pos is None:
            return None
        piece = self._game_engine.piece_at(pos)
        if piece is None:
            return None
        return self._controllers[piece.color]
