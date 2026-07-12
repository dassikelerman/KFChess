import pytest

from model.piece import PieceKind
from rules.rule_engine import PieceRuleRegistry, UnknownPieceKindError, build_default_registry
from rules.piece_rules import MovementStrategy


class DummyStrategy(MovementStrategy):
    def is_legal(self, dr, dc, context):
        return True


def test_register_and_get():
    registry = PieceRuleRegistry()
    strategy = DummyStrategy()
    registry.register(PieceKind.KNIGHT, strategy)
    assert registry.get(PieceKind.KNIGHT) is strategy


def test_unknown_kind_raises():
    registry = PieceRuleRegistry()
    with pytest.raises(UnknownPieceKindError):
        registry.get(PieceKind.QUEEN)


def test_registered_kinds_reflects_custom_registration():
    registry = PieceRuleRegistry()
    registry.register(PieceKind.KNIGHT, DummyStrategy())
    assert PieceKind.KNIGHT in registry.registered_kinds()


def test_default_registry_has_standard_pieces():
    registry = build_default_registry(pawn_direction={"w": -1, "b": 1})
    for kind in (
        PieceKind.KING,
        PieceKind.QUEEN,
        PieceKind.ROOK,
        PieceKind.BISHOP,
        PieceKind.KNIGHT,
        PieceKind.PAWN,
    ):
        assert kind in registry.registered_kinds()
