# KungFu Chess

Real-time variant of chess: moves and jumps resolve after a delay instead
of instantly, and a "jump" onto a square can intercept an incoming enemy
move.

## Project layout

```
config/    settings.py            - all constants (timing, colors, pawn config)
model/     board.py               - BoardRepresentation (abstract) + TextBoardRepresentation
           piece.py, position.py, - reserved for future use (pieces/positions are
           game_state.py            currently plain strings/tuples, not dedicated classes)
rules/     piece_rules.py         - MovementStrategy interface, MoveContext,
                                     King/Queen/Rook/Bishop/Knight/Pawn strategies
           rule_engine.py         - PieceRuleRegistry (Registry/Factory pattern),
                                     WinCondition / PromotionRule strategies
realtime/  motion.py              - Move / Jump value objects
           realtime_arbiter.py    - RealtimeArbiter (clock, in-flight motion resolution)
engine/    game_engine.py         - GameEngine (turn orchestration)
input/     board_mapper.py        - pixel -> board cell mapping
           controller.py          - command string -> engine call dispatch
board_io/  board_parser.py        - board-token parsing + board construction
           board_printer.py       - board -> text rendering
view/      renderer.py,           - reserved for future use (no graphical view exists
           image_view.py            today; rendering is text-only, see board_io/)
texttests/ script_parser.py       - splits raw input into board/commands sections
           script_runner.py       - runs a parsed script end-to-end
tests/     test_*.py              - unit tests (pytest)
app.py     entry point + dependency wiring
```

## How the 4 requirements are addressed

1. **Future binary representation** - all game logic talks only to the
   `BoardRepresentation` interface (`model/board.py`). The only
   concrete implementation today, `TextBoardRepresentation`, stores tokens
   like `"wK"`, but a future `BitboardRepresentation` could implement the
   same interface using integers internally without any other file
   changing.

2. **No hardcoded rules** - each piece's movement is a `MovementStrategy`
   registered by letter in a `PieceRuleRegistry`
   (`rules/rule_engine.py`). Registering a new kind (e.g. a custom
   "Champion" piece) automatically makes it a legal board token too, since
   `board_io/board_parser.py` derives valid tokens from the registry instead
   of a fixed string. Win conditions and promotion are likewise pluggable
   strategies (`rules/rule_engine.py`).

3. **Clean code** - one responsibility per module/class (parsing, board
   storage, movement rules, turn orchestration, real-time motion
   resolution, rendering are all separate); no duplicated logic (e.g.
   `path_is_clear` is shared by Rook/Bishop/Queen); no magic numbers (all
   constants live in `config/settings.py`); the board's internal
   list-of-lists storage is private and only reachable through its public
   interface. `GameEngine` (`engine/game_engine.py`) is a thin orchestrator:
   it delegates legality checks to the rule registry and all clock/motion
   handling to `RealtimeArbiter` (`realtime/realtime_arbiter.py`).

4. **Tests & DI** - `tests/` covers every module. `GameEngine` and
   `texttests.script_runner.run` take all collaborators (board, registry,
   win condition, promotion rule, config) as constructor/function
   arguments, so tests substitute fakes (see `tests/test_engine.py`)
   instead of monkeypatching.

## Known open item

The original code set pawn double-step eligibility with
`start_row = 1 if color == "w" else 6`, which was flagged as uncertain in
a comment (pawns are placed on row 6 for white in the sample board, so a
double step from row 1 doesn't actually apply to them). This has been
preserved as-is in `config.PAWN_START_ROW = {"w": 1, "b": 6}` rather than
silently changed - flip the values there if white's double-step should
work from row 6 instead.

## Running tests

```
pip install pytest
pytest
```

## Repository

`<insert-git-repository-url-here>` (see header comment in `app.py`)
