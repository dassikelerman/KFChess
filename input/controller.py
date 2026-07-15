class Controller:
    """Turns raw pixel clicks into board actions.

    Tracks which cell is currently selected across a click pair, and asks
    the GameEngine to judge/execute the resulting move or jump via
    request_move()/request_jump(). GameEngine itself never sees a pixel -
    only Position.
    """

    def __init__(self, game_engine, board_mapper):
        self._game_engine = game_engine
        self._board_mapper = board_mapper
        self._selected = None
        self._selected_piece_id = None

    @property
    def selected(self):
        if self._selected is None:
            return None
        return (self._selected.row, self._selected.col)

    def click(self, x, y):
        if self._game_engine.game_over:
            return

        pos = self._board_mapper.pixel_to_cell(x, y)
        if pos is None:
            return

        if self._selected is None:
            self._selected = self._select(pos)
            return

        self._act_on_selection(pos)

    def jump(self, x, y):
        self._selected = None
        self._selected_piece_id = None
        if self._game_engine.game_over:
            return

        pos = self._board_mapper.pixel_to_cell(x, y)
        if pos is None:
            return

        self._game_engine.request_jump(pos)

    # -- internal helpers -------------------------------------------------

    def _select(self, pos):
        if self._is_busy(pos):
            return None
        piece = self._game_engine.board.piece_at(pos)
        if piece is None:
            return None
        self._selected_piece_id = piece.id
        return pos

    def _act_on_selection(self, pos):
        start = self._selected
        board = self._game_engine.board
        piece = board.piece_at(start)

        # The piece originally selected may have been captured (and the
        # cell taken by a different piece) while it sat waiting for a
        # second click - e.g. an enemy motion or jump resolving on `start`
        # in between. Position alone can't tell them apart, so confirm
        # identity the same way RealTimeArbiter._resolve_arrival does.
        if piece is None or piece.id != self._selected_piece_id or self._is_busy(start):
            self._selected = None
            self._selected_piece_id = None
            return

        target = board.piece_at(pos)
        if target is not None and target.color == piece.color:
            if not self._is_busy(pos):
                self._selected = pos
                self._selected_piece_id = target.id
            return

        self._game_engine.request_move(start, pos)
        # Whether the move was accepted or the target was illegal, the
        # click pair is over: an illegal target cancels the selection
        # instead of leaving it open for another attempt - the user must
        # select the piece again from scratch.
        self._selected = None
        self._selected_piece_id = None

    def _is_busy(self, pos):
        return self._game_engine.is_position_busy(pos)
