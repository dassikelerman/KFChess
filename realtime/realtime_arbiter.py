from realtime.motion import Move, Jump


class RealtimeArbiter:
    """Owns everything about how KungFu Chess moves/jumps play out over time:
    the clock, in-flight motions, arrival/settlement, and interception
    arbitration between a landing move and a defending jump.

    Carved out of GameEngine so turn orchestration (selection, click/jump
    handling, legality checks) stays separate from real-time motion
    resolution. GameEngine drives this class through enqueue_move/
    enqueue_jump/tick/resolve/is_busy/opposite_color_moving; nothing else
    needs to know how motions are tracked internally.
    """

    def __init__(self, board, win_condition, promotion_rule, config):
        self._board = board
        self._win_condition = win_condition
        self._promotion_rule = promotion_rule
        self._config = config
        self._clock = 0
        self._active_moves = []
        self._active_jumps = []
        self._game_over = False

    @property
    def clock(self):
        return self._clock

    @property
    def game_over(self):
        return self._game_over

    def is_busy(self, cell):
        return self._is_moving_from(cell) or self._is_jumping_on(cell)

    def opposite_color_moving(self, color):
        return any(move.piece[0] != color for move in self._active_moves)

    def enqueue_move(self, piece, start, end, distance):
        self._active_moves.append(
            Move(piece, start, end, self._clock + self._config.MOVE_DURATION * distance)
        )

    def enqueue_jump(self, piece, cell):
        self._active_jumps.append(Jump(piece, cell, self._clock + self._config.JUMP_DURATION))

    def tick(self, dt):
        self._clock += dt
        self.resolve()

    def resolve(self):
        self._resolve_moves()

    # -- internal helpers -------------------------------------------------

    def _is_moving_from(self, cell):
        return any(move.start == cell for move in self._active_moves)

    def _is_jumping_on(self, cell):
        return any(jump.cell == cell for jump in self._active_jumps)

    def _resolve_moves(self):
        remaining = []
        for move in self._active_moves:
            if self._clock < move.arrival:
                remaining.append(move)
                continue
            self._settle_move(move)
        self._active_moves = remaining
        self._resolve_jumps()

    def _settle_move(self, move):
        if self._is_intercepted(move):
            if self._win_condition.is_game_over(move.piece):
                self._game_over = True
            self._board.set(*move.start, self._config.EMPTY_CELL)
            return

        r, c = move.end
        target = self._board.get(r, c)
        if target != self._config.EMPTY_CELL and target[0] == move.piece[0]:
            return

        captured = None if target == self._config.EMPTY_CELL else target
        if self._win_condition.is_game_over(captured):
            self._game_over = True

        self._board.set(*move.start, self._config.EMPTY_CELL)
        piece = self._promotion_rule.promote(move.piece, r, self._board.height)
        self._board.set(r, c, piece)

    def _is_intercepted(self, move):
        
        r, c = move.end
        return any(
            jump.cell == (r, c) and jump.piece[0] != move.piece[0]
            for jump in self._active_jumps
        )

    def _resolve_jumps(self):
        self._active_jumps = [j for j in self._active_jumps if self._clock < j.end_time]
