from dataclasses import dataclass

from model.game_state import ActionResultReason
from rules.piece_rules import MoveContext


@dataclass(frozen=True)
class MoveValidation:
    # Internal legality-check result - kept separate from ActionResult,
    # the external result of a whole request_move()/request_jump() call.
    is_valid: bool
    reason: ActionResultReason


class RuleEngine:
    def __init__(self, rule_registry):
        self._registry = rule_registry

    def validate_move(self, board, source, destination):
        piece = board.piece_at(source)
        if piece is None:
            return MoveValidation(False, ActionResultReason.EMPTY_SOURCE)

        target = board.piece_at(destination)
        if target is not None and target.color == piece.color:
            return MoveValidation(False, ActionResultReason.FRIENDLY_DESTINATION)

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
            return MoveValidation(False, ActionResultReason.ILLEGAL_PIECE_MOVE)

        return MoveValidation(True, ActionResultReason.OK)


class UnknownPieceKindError(Exception):
    pass


class IncompletePieceRuleRegistryError(Exception):
    pass


class PieceRuleRegistry:
    """Maps a PieceKind to its MovementStrategy - the extension point for
    movement rules (Strategy pattern): registering a kind with its own
    strategy is all a new piece kind needs, no engine/parser changes."""

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

    def ensure_covers(self, kinds):
        missing = [kind for kind in kinds if kind not in self._strategies]
        if missing:
            raise IncompletePieceRuleRegistryError(missing)


def build_default_registry(pawn_direction):
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
    registry.ensure_covers(PieceKind)
    return registry
