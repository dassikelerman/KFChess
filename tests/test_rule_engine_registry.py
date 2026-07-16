import pytest

from model.piece import PieceKind
from rules.rule_engine import (
    IncompletePieceRuleRegistryError,
    PieceRuleRegistry,
    UnknownPieceKindError,
    build_default_registry,
)
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


def test_default_registry_has_exactly_all_piece_kinds():
    registry = build_default_registry(pawn_direction={"w": -1, "b": 1})
    assert set(registry.registered_kinds()) == set(PieceKind)


def test_ensure_covers_passes_when_every_kind_is_registered():
    registry = PieceRuleRegistry()
    for kind in PieceKind:
        registry.register(kind, DummyStrategy())
    registry.ensure_covers(PieceKind)


def test_ensure_covers_raises_when_a_kind_is_missing():
    registry = PieceRuleRegistry()
    for kind in PieceKind:
        if kind is not PieceKind.KNIGHT:
            registry.register(kind, DummyStrategy())

    with pytest.raises(IncompletePieceRuleRegistryError):
        registry.ensure_covers(PieceKind)
