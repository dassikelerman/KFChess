import typing


class ActionSink(typing.Protocol):
    def request_move(self, source, destination): ...
    def request_jump(self, position): ...


class GameStateReader(typing.Protocol):
    @property
    def game_over(self): ...
    def piece_at(self, position): ...
    def is_busy(self, position): ...


class Controller:
    def __init__(self, action_sink: ActionSink, state_reader: GameStateReader, board_mapper):
        self._action_sink = action_sink
        self._state_reader = state_reader
        self._board_mapper = board_mapper
        self._selected = None
        self._selected_piece_id = None

    @property
    def selected(self):
        if self._selected is None:
            return None
        return (self._selected.row, self._selected.col)

    def click(self, x, y):
        if self._state_reader.game_over:
            return

        pos = self._board_mapper.pixel_to_cell(x, y)
        if pos is None:
            return

        if self._selected is None:
            self._selected = self._select(pos)
            return

        self._act_on_selection(pos)

    def jump(self, x, y):
        self._clear_selection()
        if self._state_reader.game_over:
            return

        pos = self._board_mapper.pixel_to_cell(x, y)
        if pos is None:
            return

        self._action_sink.request_jump(pos)

    def refresh_selection(self):
        """Drops a selection that's gone stale (its piece was captured,
        replaced, or is no longer selectable) without waiting for the
        next click to notice - meant to be polled once per UI frame so
        the selection frame never lingers on a piece that isn't there
        anymore."""
        if self._selected is not None and not self._selection_is_valid():
            self._clear_selection()

    # -- internal helpers -------------------------------------------------

    def _select(self, pos):
        if self._is_busy(pos):
            return None
        piece = self._state_reader.piece_at(pos)
        if piece is None:
            return None
        self._selected_piece_id = piece.id
        return pos

    def _act_on_selection(self, pos):
        start = self._selected

        # The originally selected piece may have been captured (and its
        # cell taken by a different piece) while waiting for the second
        # click - Position alone can't tell them apart, so identity is
        # confirmed the same way RealTimeArbiter._resolve_arrival does.
        if not self._selection_is_valid():
            self._clear_selection()
            return

        piece = self._state_reader.piece_at(start)
        target = self._state_reader.piece_at(pos)
        if target is not None and target.color == piece.color:
            if not self._is_busy(pos):
                self._selected = pos
                self._selected_piece_id = target.id
            return

        self._action_sink.request_move(start, pos)
        # An illegal target cancels the selection rather than leaving it
        # open for another attempt - the piece must be selected again.
        self._clear_selection()

    def _selection_is_valid(self):
        piece = self._state_reader.piece_at(self._selected)
        return (
            piece is not None
            and piece.id == self._selected_piece_id
            and not self._is_busy(self._selected)
        )

    def _clear_selection(self):
        self._selected = None
        self._selected_piece_id = None

    def _is_busy(self, pos):
        return self._state_reader.is_busy(pos)
