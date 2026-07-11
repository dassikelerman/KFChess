from model.board import TextBoardRepresentation


class BoardParseError(Exception):
    pass


def _valid_tokens(registry, colors, empty_token):
    """Valid tokens are derived from whatever piece kinds are registered,
    rather than a hardcoded string - so registering a custom piece kind
    automatically makes its token accepted here too.
    """
    tokens = {empty_token}
    for color in colors:
        for kind in registry.registered_kinds():
            tokens.add(color + kind)
    return tokens


def build_board(lines, registry, config):
    valid_tokens = _valid_tokens(registry, config.COLORS, config.EMPTY_CELL)
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
    return TextBoardRepresentation(rows, empty_token=config.EMPTY_CELL)
