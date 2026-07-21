class SnapshotView:
    def __init__(self):
        self._snapshot = None
        self._clock_ms = 0

    def update(self, game_snapshot, clock_ms):
        self._snapshot = game_snapshot
        self._clock_ms = clock_ms

    def snapshot(self):
        return self._snapshot

    @property
    def clock(self):
        return self._clock_ms

    @property
    def game_over(self):
        return self._snapshot is not None and self._snapshot.game_over

    def piece_at(self, position):
        for piece in self._pieces():
            if piece.row == position.row and piece.col == position.col:
                return piece
        return None

    def is_busy(self, position):
        piece = self.piece_at(position)
        return piece is not None and piece.is_jumping

    def _pieces(self):
        return [] if self._snapshot is None else self._snapshot.pieces
