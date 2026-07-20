"""Step 4 of the client/server migration (docs/kf-chess-architecture-plan.md):
a purely local read-model over the most recent GameSnapshot the server
sent. Satisfies the GameStateReader Protocol (input/controller.py) via
plain lookups over GameSnapshot.pieces - id, row, col, is_jumping,
rest_fraction_remaining are the only data this reads, no other source.

The client is never authoritative: any read done here can be stale by
the time it reaches the server (a piece may already have moved on),
and that's fine - the server rejects requests against its own state,
not the client's guess. Also exposes snapshot()/clock, matching what
view/game_ui_snapshot.py's build_ui_snapshot expects from "engine"."""


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
