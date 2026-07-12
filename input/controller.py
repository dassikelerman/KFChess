class Controller:
    """Turns raw pixel clicks into board actions.

    Tracks which cell is currently selected across a click pair, and asks
    the GameEngine to judge/execute the resulting move via
    request_move(). GameEngine itself never sees a pixel - only Position.
    A jump is still a UI-click decision, so it's queued straight onto the
    arbiter here, without routing through GameEngine at all.
    """

    def __init__(self, game_engine, board_mapper):
        self._game_engine = game_engine
        self._board_mapper = board_mapper
        self._selected = None

    @property
    def selected(self):
        if self._selected is None:
            return None
        return (self._selected.row, self._selected.col)

    def click(self, x, y):
        self._game_engine.wait(0)  # resolve any arrivals due before acting on this click
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
        self._game_engine.wait(0)
        self._selected = None
        if self._game_engine.game_over:
            return

        pos = self._board_mapper.pixel_to_cell(x, y)
        if pos is None:
            return

        if self._is_busy(pos):
            return

        piece = self._game_engine.board.piece_at(pos)
        if piece is None:
            return

        arbiter = self._game_engine.arbiter
        end_time = arbiter.clock + self._game_engine.jump_duration
        arbiter.start_jump(piece, pos, end_time)

    # -- internal helpers -------------------------------------------------

    def _select(self, pos):
        if self._is_busy(pos):
            return None
        piece = self._game_engine.board.piece_at(pos)
        return pos if piece is not None else None

    def _act_on_selection(self, pos):
        start = self._selected
        board = self._game_engine.board
        piece = board.piece_at(start)

        if piece is None or self._is_busy(start):
            self._selected = None
            return

        target = board.piece_at(pos)
        if target is not None and target.color == piece.color:
            if not self._is_busy(pos):
                self._selected = pos
            return

        result = self._game_engine.request_move(start, pos)
        if not result.is_accepted:
            return  # illegal target: keep current selection

        self._selected = None

    def _is_busy(self, pos):
        arbiter = self._game_engine.arbiter
        return arbiter.has_active_motion(pos) or arbiter.is_jumping_on(pos)
