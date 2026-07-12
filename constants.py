"""Raw constant values used when composing the app in app.py's build_app().

Plain module-level values only - no class, no object bundling them
together. Each one is still fed to its own component individually in
build_app(), exactly as before; this file only centralizes where the
literal values themselves are written, so they don't have to be guessed
inline in the middle of a function body.
"""

CELL_SIZE = 100
MOVE_DURATION = 1000
JUMP_DURATION = 1000
COLORS = ("w", "b")
PAWN_DIRECTION = {"w": -1, "b": 1}
EMPTY_CELL = "."
