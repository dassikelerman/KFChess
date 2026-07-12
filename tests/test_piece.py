import pytest

from model.piece import PieceKind, kind_letter, parse_kind


@pytest.mark.parametrize(
    "letter, kind",
    [
        ("K", PieceKind.KING),
        ("Q", PieceKind.QUEEN),
        ("R", PieceKind.ROOK),
        ("B", PieceKind.BISHOP),
        ("N", PieceKind.KNIGHT),
        ("P", PieceKind.PAWN),
    ],
)
def test_parse_kind_builds_matching_piece_kind(letter, kind):
    assert parse_kind(letter) is kind


def test_parse_kind_rejects_unknown_letter():
    with pytest.raises(ValueError):
        parse_kind("C")


@pytest.mark.parametrize(
    "kind, letter",
    [
        (PieceKind.KING, "K"),
        (PieceKind.QUEEN, "Q"),
        (PieceKind.ROOK, "R"),
        (PieceKind.BISHOP, "B"),
        (PieceKind.KNIGHT, "N"),
        (PieceKind.PAWN, "P"),
    ],
)
def test_kind_letter_is_the_inverse_of_parse_kind(kind, letter):
    assert kind_letter(kind) == letter
    assert parse_kind(kind_letter(kind)) is kind
