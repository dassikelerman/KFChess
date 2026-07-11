from abc import ABC, abstractmethod


class UnknownPieceKindError(Exception):
    pass


class PieceRuleRegistry:
    """Maps a piece-kind letter to its MovementStrategy.

    This is the extension point required for custom games: registering a
    new kind (e.g. "C" for a custom "Champion" piece) with its own
    MovementStrategy is all that's needed to support it - no engine or
    parser code has to change, and the piece automatically becomes a
    valid board token (see game.parser).
    """

    def __init__(self):
        self._strategies = {}

    def register(self, kind, strategy):
        self._strategies[kind] = strategy

    def get(self, kind):
        try:
            return self._strategies[kind]
        except KeyError:
            raise UnknownPieceKindError(kind) from None

    def registered_kinds(self):
        return tuple(self._strategies.keys())


def build_default_registry(config):
    """Factory for the standard chess piece set.

    Kept separate from PieceRuleRegistry itself so alternate registries
    (e.g. for a custom variant) can be assembled the same way without
    subclassing anything.
    """
    from rules.piece_rules import (
        KingMovement,
        QueenMovement,
        RookMovement,
        BishopMovement,
        KnightMovement,
        PawnMovement,
    )

    registry = PieceRuleRegistry()
    registry.register("K", KingMovement())
    registry.register("Q", QueenMovement())
    registry.register("R", RookMovement())
    registry.register("B", BishopMovement())
    registry.register("N", KnightMovement())
    registry.register("P", PawnMovement(config.PAWN_DIRECTION))
    return registry


class WinCondition(ABC):
    """Decides whether a capture ends the game (Strategy pattern).

    Swappable so custom variants can define a different win condition
    (e.g. capture-the-flag, last-piece-standing) without touching the
    engine.
    """

    @abstractmethod
    def is_game_over(self, captured_piece):
        """captured_piece is the token that was just captured, or None."""


class KingCaptureWinCondition(WinCondition):
    def is_game_over(self, captured_piece):
        return captured_piece is not None and captured_piece[1] == "K"


class PromotionRule(ABC):
    """Decides whether/how a piece transforms after moving (Strategy pattern)."""

    @abstractmethod
    def promote(self, piece, row, board_height):
        """Return the (possibly unchanged) piece token after promotion rules apply."""


class LastRankPromotion(PromotionRule):
    def __init__(self, promotable_kind="P", promote_to="Q"):
        self._promotable_kind = promotable_kind
        self._promote_to = promote_to

    def promote(self, piece, row, board_height):
        color, kind = piece[0], piece[1]
        if kind != self._promotable_kind:
            return piece
        last_rank = 0 if color == "w" else board_height - 1
        if row == last_rank:
            return color + self._promote_to
        return piece
