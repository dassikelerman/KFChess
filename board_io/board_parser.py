from model.board import Board
from model.piece import PieceKind, kind_letter


class BoardParseError(Exception):
    pass


def parse_input(lines):
    """Split raw input lines into the 'Board:' and 'Commands:' sections."""
    board_lines, commands = [], []
    section = None
    for line in lines:
        if line == "Board:":
            section = "board"
            continue
        if line == "Commands:":
            section = "commands"
            continue
        if section == "board":
            board_lines.append(line)
        elif section == "commands":
            commands.append(line)
    return board_lines, commands


def _valid_tokens(colors, empty_token):
    """Valid tokens are derived from PieceKind - the single source of
    truth for every piece kind a (complete) PieceRuleRegistry covers -
    rather than a hardcoded string.
    """
    tokens = {empty_token}
    for color in colors:
        for kind in PieceKind:
            tokens.add(color + kind_letter(kind))
    return tokens


def build_board(lines, registry, colors, empty_cell):
    registry.ensure_covers(PieceKind)
    valid_tokens = _valid_tokens(colors, empty_cell)
    rows = []
    width = None
    for line in lines:
        tokens = line.split()
        if not tokens:
            continue
        if width is None:
            width = len(tokens)
        elif len(tokens) != width:
            raise BoardParseError("ROW_WIDTH_MISMATCH")
        for token in tokens:
            if token not in valid_tokens:
                raise BoardParseError("UNKNOWN_TOKEN")
        rows.append(tokens)
    return Board(rows, empty_token=empty_cell)
