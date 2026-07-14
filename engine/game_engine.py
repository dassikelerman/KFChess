from dataclasses import replace

from model.game_state import GameSnapshot, MoveResult, PieceSnapshot
from model.piece import AnimationState, PieceColor, kind_letter, parse_kind


def _token(piece):
    return piece.color.value + kind_letter(piece.kind)


def _captured_token(event):
    """A minimal placeholder token for WinCondition.is_game_over(), which
    only ever inspects the kind character - the real captured piece is
    already gone from the board by the time an ArrivalEvent is reported,
    and the event deliberately only carries whether it was a king.
    """
    if event.captured_piece_id is None:
        return None
    return "?K" if event.king_captured else "??"


class GameEngine:
    """Judges and executes moves, and resolves in-flight arrivals over
    time. Knows nothing about pixels or clicks - that's the input
    layer's job (input.controller.Controller); this class only ever
    deals in Position/Piece and board/arbiter state.

    All collaborators (board, rule engine, real-time arbiter, win
    condition, promotion rule, move/jump durations) are injected through
    the constructor - no module-level state, no hidden globals.
    """

    def __init__(
        self, board, rule_engine, arbiter, win_condition, promotion_rule, move_duration, jump_duration
    ):
        if move_duration <= 0:
            raise ValueError("move_duration must be positive")
        if jump_duration <= 0:
            raise ValueError("jump_duration must be positive")

        self._board = board
        self._rule_engine = rule_engine
        self._arbiter = arbiter
        self._win_condition = win_condition
        self._promotion_rule = promotion_rule
        self._move_duration = move_duration
        self._jump_duration = jump_duration
        self._game_over = False

    @property
    def game_over(self):
        return self._game_over

    @property
    def clock(self):
        return self._arbiter.clock

    @property
    def board(self):
        return self._board

    @property
    def arbiter(self):
        return self._arbiter

    @property
    def jump_duration(self):
        return self._jump_duration

    def request_move(self, source, destination):
        if self._game_over:
            return MoveResult(False, "game_over")

        if self._arbiter.has_active_motion(source):
            return MoveResult(False, "motion_in_progress")

        if self._arbiter.is_jumping_on(source):
            return MoveResult(False, "jump_in_progress")

        validation = self._rule_engine.validate_move(self._board, source, destination)
        if not validation.is_valid:
            return MoveResult(False, validation.reason)

        piece = self._board.piece_at(source)
        distance = max(abs(destination.row - source.row), abs(destination.col - source.col))
        duration_ms = self._move_duration * distance
        self._arbiter.start_motion(piece, source, destination, duration_ms)
        return MoveResult(True, "ok")

    def is_position_busy(self, position):
        return self._arbiter.has_active_motion(position) or self._arbiter.is_jumping_on(position)

    def request_jump(self, position):
        
        if self._game_over:
            return MoveResult(False, "game_over")
        
        if self.is_position_busy(position):
            return

        piece = self._board.piece_at(position)
        if piece is None:
            return

        end_time = self._arbiter.clock + self._jump_duration
        self._arbiter.start_jump(position, end_time)

    def wait(self, dt):
        self._advance(dt)

    def snapshot(self):
        pieces = [self._piece_snapshot(piece) for piece in self._board.pieces()]
        return GameSnapshot(
            board_width=self._board.width,
            board_height=self._board.height,
            pieces=pieces,
            game_over=self._game_over,
        )

    # -- internal helpers -------------------------------------------------

    def _piece_snapshot(self, piece):
        motion = self._arbiter.active_motion_for(piece.id)
        if motion is not None:
            render_row, render_col = self._interpolated_position(motion)
            animation_state = AnimationState.MOVE
        elif self._arbiter.active_jump_for(piece.cell) is not None:
            render_row, render_col = float(piece.cell.row), float(piece.cell.col)
            animation_state = AnimationState.JUMP
        else:
            render_row, render_col = float(piece.cell.row), float(piece.cell.col)
            # TODO: LONG_REST (just finished a move) / SHORT_REST (just
            # finished a jump) are intentionally not distinguished from
            # genuine idle here - see AnimationState's docstring for why,
            # and how a view can derive them itself instead.
            animation_state = AnimationState.IDLE

        return PieceSnapshot(
            id=piece.id,
            kind=piece.kind,
            color=piece.color,
            state=piece.state,
            row=piece.cell.row,
            col=piece.cell.col,
            render_row=render_row,
            render_col=render_col,
            animation_state=animation_state,
        )

    def _interpolated_position(self, motion):
        progress = motion.progress_at(self._arbiter.clock)
        row = motion.source.row + (motion.destination.row - motion.source.row) * progress
        col = motion.source.col + (motion.destination.col - motion.source.col) * progress
        return row, col

    def _advance(self, ms):
        events = self._arbiter.advance_time(ms)
        self._apply_events(events)

    def _apply_events(self, events):
        for event in events:
            if self._win_condition.is_game_over(_captured_token(event)):
                self._game_over = True
                return 

            if event.captured_piece_id == event.piece_id:
                continue  # the arriving piece was intercepted: nothing landed to promote

            moved = self._board.piece_at(event.destination)
            if moved is None or moved.id != event.piece_id:
                # event.destination was overwritten by a later event in this
                # same batch (e.g. another motion capturing the same cell)
                # before this event was processed - the piece this event
                # actually reports on is already gone, so there's nothing of
                # its own left to promote. The event that truly landed there
                # gets its own correctly-attributed pass through this loop.
                continue
            promoted_token = self._promotion_rule.promote(
                _token(moved), event.destination.row, self._board.height
            )
            promoted = replace(
                moved, color=PieceColor(promoted_token[0]), kind=parse_kind(promoted_token[1])
            )
            self._board.add_piece(promoted)
