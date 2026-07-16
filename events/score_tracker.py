from model.piece import PieceColor, PieceKind

from events.game_events import CaptureEvent

SCORE_BY_KIND = {
    PieceKind.PAWN: 1,
    PieceKind.KNIGHT: 3,
    PieceKind.BISHOP: 3,
    PieceKind.ROOK: 5,
    PieceKind.QUEEN: 9,
    PieceKind.KING: 0,  # a king capture ends the game, not a score race
}


class ScoreTracker:
    def __init__(self, dispatcher):
        self._score = {PieceColor.WHITE: 0, PieceColor.BLACK: 0}
        dispatcher.subscribe(CaptureEvent, self._on_capture)

    def _on_capture(self, event):
        self._score[event.piece_color] += SCORE_BY_KIND[event.captured_kind]

    def snapshot(self):
        return dict(self._score)
