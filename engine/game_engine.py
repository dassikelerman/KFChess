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
        self,
        board,
        rule_engine,
        arbiter,
        win_condition,
        promotion_rule,
        move_duration,
        jump_duration,
        long_rest_duration,
        short_rest_duration,
    ):
        if move_duration <= 0:
            raise ValueError("move_duration must be positive")
        if jump_duration <= 0:
            raise ValueError("jump_duration must be positive")
        # Unlike move/jump duration, 0 is a legitimate value here - it
        # means "no cooldown" (is_resting() is a plain clock comparison,
        # with none of the degenerate-Motion edge cases a zero move/jump
        # duration caused), so only reject negative values.
        if long_rest_duration < 0:
            raise ValueError("long_rest_duration must not be negative")
        if short_rest_duration < 0:
            raise ValueError("short_rest_duration must not be negative")

        self._board = board
        self._rule_engine = rule_engine
        self._arbiter = arbiter
        self._win_condition = win_condition
        self._promotion_rule = promotion_rule
        self._move_duration = move_duration
        self._jump_duration = jump_duration
        self._long_rest_duration = long_rest_duration
        self._short_rest_duration = short_rest_duration
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

        if self._arbiter.is_jumping_on(source):
            return MoveResult(False, "jump_in_progress")

        # A piece already mid-flight has already left source on the Board
        # the instant its own motion started (see RealTimeArbiter.
        # start_motion), so there's nothing there for validate_move() to
        # find - it already rejects this as "empty_source" below, without
        # needing its own has_active_motion() check.
        piece = self._board.piece_at(source)
        if piece is not None and self._arbiter.is_resting(piece.id):
            return MoveResult(False, "resting")

        validation = self._rule_engine.validate_move(self._board, source, destination)
        if not validation.is_valid:
            return MoveResult(False, validation.reason)

        # The Board shows a departing piece's old cell as empty (see
        # above), so validate_move() alone can't tell "genuinely empty"
        # apart from "a teammate just left here". A same-color piece must
        # still be kept out of that cell, same as if the teammate were
        # still sitting there; an enemy is free to move into it.
        departing = self._arbiter.active_motion_from(destination)
        if departing is not None and departing.piece.color == piece.color:
            return MoveResult(False, "friendly_departure_cell")

        distance = max(abs(destination.row - source.row), abs(destination.col - source.col))
        duration_ms = self._move_duration * distance
        self._arbiter.start_motion(piece, source, destination, duration_ms)
        return MoveResult(True, "ok")

    def is_position_busy(self, position):
        # A piece leaves the Board the instant its own motion starts (see
        # RealTimeArbiter.start_motion), so whatever currently occupies
        # `position` - if anything - can never be the piece behind an
        # active motion sourced from here; that motion is about a
        # different, already-departed piece, irrelevant to selecting or
        # jump-guarding whatever's actually here now. Only an active jump
        # can make a still-present piece busy.
        return self._arbiter.is_jumping_on(position)

    def request_jump(self, position):
        
        if self._game_over:
            return MoveResult(False, "game_over")
        
        if self.is_position_busy(position):
            return

        piece = self._board.piece_at(position)
        if piece is None:
            return

        if self._arbiter.is_resting(piece.id):
            return

        end_time = self._arbiter.clock + self._jump_duration
        self._arbiter.start_jump(position, end_time)

    def wait(self, dt):
        self._advance(dt)

    def snapshot(self):
        # A piece leaves the Board the instant its own motion starts (see
        # RealTimeArbiter.start_motion), so board.pieces() alone would
        # silently drop every in-flight piece from rendering - each one
        # is added back here from the arbiter's own active motions.
        pieces = [self._settled_piece_snapshot(piece) for piece in self._board.pieces()]
        pieces += [self._in_flight_piece_snapshot(motion) for motion in self._arbiter.active_motions()]
        return GameSnapshot(
            board_width=self._board.width,
            board_height=self._board.height,
            pieces=pieces,
            game_over=self._game_over,
        )

    # -- internal helpers -------------------------------------------------

    def _settled_piece_snapshot(self, piece):
        # A piece from board.pieces() is never mid-flight - only
        # in-flight pieces (handled separately below) ever have an
        # active motion - so only jump/idle apply here.
        if self._arbiter.active_jump_for(piece.cell) is not None:
            animation_state = AnimationState.JUMP
        else:
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
            render_row=float(piece.cell.row),
            render_col=float(piece.cell.col),
            animation_state=animation_state,
        )

    def _in_flight_piece_snapshot(self, motion):
        # row/col report the piece's *source* - the same cell it would
        # have reported while "still there" under the old model - so
        # text rendering (an int grid) has a single definite cell to show
        # it at until it actually lands; render_row/col carry the real,
        # continuously interpolated position for animation.
        render_row, render_col = self._interpolated_position(motion)
        piece = motion.piece
        return PieceSnapshot(
            id=piece.id,
            kind=piece.kind,
            color=piece.color,
            state=piece.state,
            row=motion.source.row,
            col=motion.source.col,
            render_row=render_row,
            render_col=render_col,
            animation_state=AnimationState.MOVE,
        )

    def _interpolated_position(self, motion):
        progress = motion.progress_at(self._arbiter.clock)
        row = motion.source.row + (motion.destination.row - motion.source.row) * progress
        col = motion.source.col + (motion.destination.col - motion.source.col) * progress
        return row, col

    def _advance(self, ms):
        # A jump's own guard window ending isn't reported as an event by
        # advance_time() (it's silently dropped from _active_jumps), so
        # the pieces about to come off cooldown-triggering jumps are
        # captured here, before that happens, to apply the short-rest
        # cooldown to each once advance_time() has run.
        new_clock = self._arbiter.clock + ms
        expiring_jump_pieces = [
            self._board.piece_at(jump.cell)
            for jump in self._arbiter.active_jumps()
            if jump.end_time <= new_clock
        ]

        events = self._arbiter.advance_time(ms)

        for piece in expiring_jump_pieces:
            if piece is not None:
                self._arbiter.set_cooldown(piece.id, new_clock + self._short_rest_duration)

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
                # its own left to promote (or rest - see the same check's
                # use for the cooldown below).
                continue

            # The piece truly landed here (as opposed to a mid-flight
            # collision capture that continues on - see the check above),
            # so its walk is over: start its long-rest cooldown.
            self._arbiter.set_cooldown(moved.id, self._arbiter.clock + self._long_rest_duration)

            promoted_token = self._promotion_rule.promote(
                _token(moved), event.destination.row, self._board.height
            )
            promoted = replace(
                moved, color=PieceColor(promoted_token[0]), kind=parse_kind(promoted_token[1])
            )
            self._board.add_piece(promoted)
