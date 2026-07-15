from model.piece import PieceColor


class ClickRouter:
    """Routes a raw pixel click to one of two Controllers (one per color),
    without adding any color-awareness to Controller itself.

    A select-then-act is always a two-click gesture. The color of the
    piece under the *first* click of a gesture decides which Controller
    owns the whole gesture; every click after that (however many it
    takes - an illegal target cancels the selection, same as it does on
    a single Controller, see Controller._act_on_selection) is routed to
    that same Controller. Once that Controller's own selection clears -
    a successful move, an illegal target, or a first click that never
    selected anything - the router is free again to route the next click
    by whatever's under it.

    jump() has no two-click gesture to own - it's routed purely by the
    color of the piece under the click, same as a fresh click would be.
    """

    def __init__(self, board, board_mapper, controller_white, controller_black):
        self._board = board
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
        # Controller.jump() always clears that Controller's own selection
        # - if it happened to be the one mid-gesture, that gesture is
        # over too, and the router is free again.
        if self._active is controller:
            self._active = None

    def _controller_for(self, x, y):
        pos = self._board_mapper.pixel_to_cell(x, y)
        if pos is None:
            return None
        piece = self._board.piece_at(pos)
        if piece is None:
            return None
        return self._controllers[piece.color]
