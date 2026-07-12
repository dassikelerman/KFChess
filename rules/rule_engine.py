from dataclasses import dataclass

from rules.piece_rules import MoveContext


@dataclass(frozen=True)
class MoveValidation:
    is_valid: bool
    reason: str


class RuleEngine:
    """Decides whether a move from source to destination is legal, given
    the current board state.

    A stateless service: it only reads the board it's given and never
    mutates anything or moves any piece. That keeps it independent of
    GameEngine's own turn/timing state (selection, in-flight moves,
    jumps), so it can be reused or tested on its own.
    """

    def __init__(self, rule_registry):
        self._registry = rule_registry

    def validate_move(self, board, source, destination):
        piece = board.piece_at(source)
        if piece is None:
            return MoveValidation(False, "empty_source")

        target = board.piece_at(destination)
        if target is not None and target.color == piece.color:
            return MoveValidation(False, "friendly_destination")

        strategy = self._registry.get(piece.kind)
        dr = destination.row - source.row
        dc = destination.col - source.col
        context = MoveContext(
            board=board,
            color=piece.color.value,
            start=source,
            end=destination,
            target_occupied=target is not None,
        )
        if not strategy.is_legal(dr, dc, context):
            return MoveValidation(False, "illegal_piece_move")

        return MoveValidation(True, "ok")


class UnknownPieceKindError(Exception):
    pass


class PieceRuleRegistry:
    """Maps a PieceKind to its MovementStrategy.

    This is the extension point for movement rules: registering a
    PieceKind with its own MovementStrategy is all that's needed to
    support it - no engine or parser code has to change, and the piece
    automatically becomes a valid board token (see board_io.board_parser).
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


def build_default_registry(pawn_direction):
    """Factory for the standard chess piece set.

    Kept separate from PieceRuleRegistry itself so alternate registries
    (e.g. for a custom variant) can be assembled the same way without
    subclassing anything.
    """
    from model.piece import PieceKind
    from rules.piece_rules import (
        KingMovement,
        QueenMovement,
        RookMovement,
        BishopMovement,
        KnightMovement,
        PawnMovement,
    )

    registry = PieceRuleRegistry()
    registry.register(PieceKind.KING, KingMovement())
    registry.register(PieceKind.QUEEN, QueenMovement())
    registry.register(PieceKind.ROOK, RookMovement())
    registry.register(PieceKind.BISHOP, BishopMovement())
    registry.register(PieceKind.KNIGHT, KnightMovement())
    registry.register(PieceKind.PAWN, PawnMovement(pawn_direction))
    return registry
