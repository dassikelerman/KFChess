from dataclasses import replace

from engine.snapshot import GameSnapshot, PieceSnapshot
from events.game_events import (
    CaptureEvent,
    GameOverEvent,
    JumpCompletedEvent,
    MotionStoppedEvent,
    MoveCompletedEvent,
    PromotionEvent,
)
from model.game_state import JumpEndedEvent, MoveResult
from model.piece import PieceColor, kind_letter, parse_kind


def _token(piece):
    return piece.color.value + kind_letter(piece.kind)


def _captured_token(arrival):
    # The real captured piece is already gone from the board by the time
    # an ArrivalEvent is reported, so this is just enough of a fake token
    # (kind character only) for WinCondition.is_game_over() to read.
    if arrival.captured_piece_id is None:
        return None
    return "?K" if arrival.king_captured else "??"


def _other_color(color):
    return PieceColor.BLACK if color == PieceColor.WHITE else PieceColor.WHITE


class GameEngine:
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
        dispatcher=None,
    ):
        if move_duration <= 0:
            raise ValueError("move_duration must be positive")
        if jump_duration <= 0:
            raise ValueError("jump_duration must be positive")
        # 0 is a legitimate rest duration ("no cooldown"), unlike move/jump
        # duration where it causes degenerate-Motion edge cases.
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
        self._dispatcher = dispatcher
        self._game_over = False

    @property
    def game_over(self):
        return self._game_over

    @property
    def clock(self):
        return self._arbiter.clock

    @property
    def arbiter(self):
        return self._arbiter

    def piece_at(self, position):
        return self._board.piece_at(position)

    # -- Moves ----------------------------------------------------------------

    def request_move(self, source, destination):
        if self._game_over:
            return MoveResult(False, "game_over")

        if self._arbiter.is_jumping_on(source):
            return MoveResult(False, "jump_in_progress")

        piece = self._board.piece_at(source)
        if piece is not None and self._arbiter.is_resting(piece.id):
            return MoveResult(False, "resting")

        validation = self._rule_engine.validate_move(self._board, source, destination)
        if not validation.is_valid:
            return MoveResult(False, validation.reason)

        distance = max(abs(destination.row - source.row), abs(destination.col - source.col))
        duration_ms = self._move_duration * distance
        self._arbiter.start_motion(piece, source, destination, duration_ms)
        return MoveResult(True, "ok")

    # -- Jumps ------------------------------------------------------------------

    def is_busy(self, position):
        return self._arbiter.is_jumping_on(position)

    def request_jump(self, position):
        if self._game_over:
            return MoveResult(False, "game_over")

        if self.is_busy(position):
            return

        piece = self._board.piece_at(position)
        if piece is None:
            return

        if self._arbiter.is_resting(piece.id):
            return

        end_time = self._arbiter.clock + self._jump_duration
        self._arbiter.start_jump(position, end_time)

    # -- Event handling -----------------------------------------------------

    def wait(self, ms):
        self._advance(ms)

    def _advance(self, ms):
        events = self._arbiter.advance_time(ms)

        arrivals = []
        for event in events:
            if isinstance(event, JumpEndedEvent):
                self._arbiter.set_cooldown(event.piece_id, self._short_rest_duration)
                self._publish_jump_completed(event)
            else:
                arrivals.append(event)

        self._apply_arrivals(arrivals)

    def _apply_arrivals(self, arrivals):
        for arrival in arrivals:
            if self._win_condition.is_game_over(_captured_token(arrival)):
                self._publish_action_event(arrival)
                self._game_over = True
                self._publish(GameOverEvent(
                    winner_color=_other_color(arrival.captured_color), at_ms=self.clock,
                ))
                return

            self._publish_action_event(arrival)

            if arrival.captured_piece_id == arrival.piece_id:
                continue  # intercepted mid-flight: nothing landed to promote

            moved = self._board.piece_at(arrival.destination)
            if moved is None or moved.id != arrival.piece_id:
                # destination was overwritten by a later event in this same
                # batch before this one was processed - nothing of this
                # piece is left here to promote or rest.
                continue

            self._arbiter.set_cooldown(moved.id, self._long_rest_duration)

            before_token = _token(moved)
            promoted_token = self._promotion_rule.promote(
                before_token, arrival.destination.row, self._board.height
            )
            promoted = replace(
                moved, color=PieceColor(promoted_token[0]), kind=parse_kind(promoted_token[1])
            )
            self._board.add_piece(promoted)

            if promoted_token != before_token:
                self._publish(PromotionEvent(
                    piece_id=moved.id, piece_color=promoted.color,
                    from_kind=moved.kind, to_kind=promoted.kind,
                    at=arrival.destination, at_ms=self.clock,
                ))

    # -- Event publishing (side-channel notifications; never affects game state) --

    def _publish_action_event(self, arrival):
        if self._dispatcher is None or self._game_over:
            return
        if arrival.captured_piece_id == arrival.piece_id:
            self._dispatcher.publish(MotionStoppedEvent(
                piece_id=arrival.piece_id, piece_kind=arrival.piece_kind,
                piece_color=arrival.piece_color, at=arrival.destination, at_ms=self.clock,
            ))
        elif arrival.captured_piece_id is not None:
            self._dispatcher.publish(CaptureEvent(
                piece_id=arrival.piece_id, piece_kind=arrival.piece_kind,
                piece_color=arrival.piece_color,
                captured_piece_id=arrival.captured_piece_id,
                captured_kind=arrival.captured_kind, captured_color=arrival.captured_color,
                at=arrival.destination, at_ms=self.clock,
            ))
        else:
            self._dispatcher.publish(MoveCompletedEvent(
                piece_id=arrival.piece_id, piece_kind=arrival.piece_kind,
                piece_color=arrival.piece_color, destination=arrival.destination, at_ms=self.clock,
            ))

    def _publish_jump_completed(self, event):
        if self._dispatcher is None or self._game_over:
            return
        self._dispatcher.publish(JumpCompletedEvent(
            piece_id=event.piece_id, piece_kind=event.piece_kind,
            piece_color=event.piece_color, cell=event.cell, at_ms=self.clock,
        ))

    def _publish(self, event):
        if self._dispatcher is not None:
            self._dispatcher.publish(event)

    # -- Snapshot ---------------------------------------------------------------

    def snapshot(self):
        pieces = [self._settled_piece_snapshot(piece) for piece in self._board.pieces()]
        pieces += [self._in_flight_piece_snapshot(motion) for motion in self._arbiter.active_motions()]
        return GameSnapshot(
            board_width=self._board.width,
            board_height=self._board.height,
            pieces=pieces,
            game_over=self._game_over,
        )

    def _settled_piece_snapshot(self, piece):
        return PieceSnapshot(
            id=piece.id,
            kind=piece.kind,
            color=piece.color,
            row=piece.cell.row,
            col=piece.cell.col,
            render_row=float(piece.cell.row),
            render_col=float(piece.cell.col),
            is_moving=False,
            is_jumping=self._arbiter.is_jumping_on(piece.cell),
            rest_fraction_remaining=self._arbiter.rest_remaining_fraction(piece.id),
        )

    def _in_flight_piece_snapshot(self, motion):
        render_row, render_col = self._interpolated_position(motion)
        piece = motion.piece
        return PieceSnapshot(
            id=piece.id,
            kind=piece.kind,
            color=piece.color,
            row=motion.source.row,
            col=motion.source.col,
            render_row=render_row,
            render_col=render_col,
            is_moving=True,
            is_jumping=False,
            rest_fraction_remaining=None,
        )

    def _interpolated_position(self, motion):
        progress = motion.progress_at(self._arbiter.clock)
        row = motion.source.row + (motion.destination.row - motion.source.row) * progress
        col = motion.source.col + (motion.destination.col - motion.source.col) * progress
        return row, col
