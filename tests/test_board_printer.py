from board_io.board_printer import BoardPrinter
from engine.snapshot import GameSnapshot, PieceSnapshot
from model.piece import PieceColor, PieceKind


def piece(token, row, col):
    return PieceSnapshot(
        id=f"{token}@{row},{col}",
        kind=PieceKind(token[1]),
        color=PieceColor(token[0]),
        row=row,
        col=col,
        render_row=float(row),
        render_col=float(col),
        is_moving=False,
        is_jumping=False,
        rest_fraction_remaining=None,
    )


def snapshot(width, height, pieces):
    return GameSnapshot(
        board_width=width,
        board_height=height,
        pieces=pieces,
        game_over=False,
    )


def test_render_single_row():
    snap = snapshot(3, 1, [piece("wK", 0, 0), piece("bK", 0, 2)])
    assert BoardPrinter().render(snap) == "wK . bK"


def test_render_multiple_rows():
    snap = snapshot(3, 2, [piece("wK", 0, 0), piece("bK", 0, 2)])
    assert BoardPrinter().render(snap) == "wK . bK\n. . ."


def test_render_empty_board():
    snap = snapshot(0, 0, [])
    assert BoardPrinter().render(snap) == ""


def test_render_reflects_mutations():
    snap = snapshot(3, 1, [piece("wK", 0, 0), piece("wQ", 0, 1), piece("bK", 0, 2)])
    assert BoardPrinter().render(snap) == "wK wQ bK"
