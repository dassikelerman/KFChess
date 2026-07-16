class Controller:
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
        piece = self._game_engine.piece_at(pos)
        if piece is None:
            return None
        self._selected_piece_id = piece.id
        return pos

    def _act_on_selection(self, pos):
        start = self._selected
        piece = self._game_engine.piece_at(start)

        # The originally selected piece may have been captured (and its
        # cell taken by a different piece) while waiting for the second
        # click - Position alone can't tell them apart, so identity is
        # confirmed the same way RealTimeArbiter._resolve_arrival does.
        if piece is None or piece.id != self._selected_piece_id or self._is_busy(start):
            self._selected = None
            self._selected_piece_id = None
            return

        target = self._game_engine.piece_at(pos)
        if target is not None and target.color == piece.color:
            if not self._is_busy(pos):
                self._selected = pos
                self._selected_piece_id = target.id
            return

        self._game_engine.request_move(start, pos)
        # An illegal target cancels the selection rather than leaving it
        # open for another attempt - the piece must be selected again.
        self._selected = None
        self._selected_piece_id = None

    def _is_busy(self, pos):
        return self._game_engine.is_busy(pos)
