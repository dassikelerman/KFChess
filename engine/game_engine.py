from input.board_mapper import pixel_to_cell
from realtime.realtime_arbiter import RealtimeArbiter
from rules.piece_rules import MoveContext


class GameEngine:
    """Orchestrates KungFu Chess turns: clicks, jumps, waiting, and move
    resolution.

    All collaborators (board, rule registry, win condition, promotion
    rule, config) are injected through the constructor - no module-level
    state, no hidden globals. That makes the engine straightforward to
    unit test with fakes/stubs instead of monkeypatching.

    GameEngine itself only handles selection and turn flow: it checks game
    state, asks the rule registry whether a move is legal, and - if so -
    hands the motion off to a RealtimeArbiter, which owns the clock and
    all in-flight move/jump resolution.
    """

    def __init__(self, board, rule_registry, win_condition, promotion_rule, config):
        self._board = board
        self._registry = rule_registry
        self._config = config
        self._arbiter = RealtimeArbiter(board, win_condition, promotion_rule, config)
        self._selected = None

    @property
    def game_over(self):
        return self._arbiter.game_over

    @property
    def clock(self):
        return self._arbiter.clock

    @property
    def selected(self):
        return self._selected

    def wait(self, dt):
        self._arbiter.tick(dt)

    def render(self, renderer):
        self._arbiter.resolve()
        return renderer.render(self._board)

    def handle_click(self, x, y):
        self._arbiter.resolve()
        if self._arbiter.game_over:
            return

        cell = pixel_to_cell(x, y, self._board, self._config)
        if cell is None:
            return

        if self._selected is None:
            self._selected = self._select(cell)
            return

        self._act_on_selection(cell)

    def handle_jump(self, x, y):
        self._arbiter.resolve()
        self._selected = None
        if self._arbiter.game_over:
            return

        cell = pixel_to_cell(x, y, self._board, self._config)
        if cell is None:
            return

        if self._arbiter.is_busy(cell):
            return

        piece = self._board.get(*cell)
        if piece == self._config.EMPTY_CELL:
            return

        self._arbiter.enqueue_jump(piece, cell)

    # -- internal helpers -------------------------------------------------

    def _select(self, cell):
        if self._arbiter.is_busy(cell):
            return None
        return cell if self._board.get(*cell) != self._config.EMPTY_CELL else None

    def _act_on_selection(self, cell):
        start = self._selected
        piece = self._board.get(*start)

        if piece == self._config.EMPTY_CELL or self._arbiter.is_busy(start):
            self._selected = None
            return

        target = self._board.get(*cell)
        if target != self._config.EMPTY_CELL and target[0] == piece[0]:
            if not self._arbiter.is_busy(cell):
                self._selected = cell
            return

        if not self._is_legal_move(piece, start, cell):
            return  # illegal target: keep current selection

        if self._arbiter.opposite_color_moving(piece[0]):
            return  # opposing color has a move in flight: keep current selection

        distance = max(abs(cell[0] - start[0]), abs(cell[1] - start[1]))
        self._arbiter.enqueue_move(piece, start, cell, distance)
        self._selected = None

    def _is_legal_move(self, piece, start, end):
        strategy = self._registry.get(piece[1])
        dr, dc = end[0] - start[0], end[1] - start[1]
        context = MoveContext(
            board=self._board,
            color=piece[0],
            start=start,
            end=end,
            target_occupied=not self._board.is_empty(*end),
        )
        return strategy.is_legal(dr, dc, context)
