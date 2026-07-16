# Design decisions and rationale

This file collects the "why" behind non-obvious behavior in the codebase,
consolidated out of inline comments so the code itself stays short and
readable. Code keeps only short, local comments for things that would
otherwise be easy to break by accident; broader architectural reasoning
lives here.

## Real-time motion model (`realtime/`)

A piece leaves the `Board` the **instant** its `Motion` starts, not when
it arrives (`RealTimeArbiter.start_motion` calls `board.remove_piece`
immediately). While airborne, the piece's full identity (id/color/kind)
lives only on the `Motion` object itself - nothing else can capture or
block it at its old cell in the meantime, and a different piece is free
to move into that now-empty cell (including a teammate - see "Removal
of friendly_departure_cell" below).

`start_time`/`arrival_time` are absolute clock values, not relative
durations, so resolution order is judged by when a motion actually
lands, not by the order motions were queued in.

### In-transit collisions

`advance_time()` resolves every arrival and in-transit collision due by
the new clock value in **strict chronological order**, recomputing the
next event fresh after each one (an arrival removes a motion; a
collision removes or truncates one). This makes the outcome identical
whether a span is covered by one big `wait()` or many small ones -
covered by `test_same_result_for_one_big_wait_as_for_several_small_waits`.

Collision resolution policy, by actual arrival time at the shared cell:

- **Same color, non-tied**: the earlier motion continues untouched: the
  later one stops one cell short (`Motion.truncate_before`).
- **Different color, non-tied**: the later arrival captures the earlier
  one and continues on to its own original destination.
- **Same color, exact tie**: no well-defined first/second, so both stop
  one cell short of the contested cell.
- **Different color, exact tie**: no well-defined winner, so **both are
  destroyed** - a deliberate, documented, deterministic policy rather
  than an arbitrary tie-break.

A knight's L-shaped move isn't a line it travels along, and already
ignores blockers for legality purposes, so it has no in-transit cells
to collide on - only its destination counts (`Motion.path_cells`).

### Removal of friendly_departure_cell (2026-07-16)

Earlier, a same-color piece was blocked from moving into a cell a
teammate's motion had just departed (while an enemy could). That rule
has been removed: once a piece's source cell is vacated, **any** piece
- same color or not - may move into it. `RealTimeArbiter.active_motion_from`
and `has_active_motion` (which existed only to support that rule) were
removed along with it, since nothing else used them.

## Cooldown / rest system

After a move lands, a piece enters a `LONG_REST_DURATION` cooldown; after
a jump's guard window ends, a `SHORT_REST_DURATION` cooldown. Unlike
`move_duration`/`jump_duration`, `0` is a legitimate rest duration
("no cooldown") - `RealTimeArbiter.is_resting` is a plain clock
comparison with none of the degenerate-`Motion` edge cases a zero
move/jump duration would cause.

Cooldown must only start once a piece **truly lands** - not at an
earlier instant it captured another piece mid-flight and continued on.
`GameEngine._apply_events` reuses the same identity check
(`moved.id == event.piece_id`) for both this and promotion attribution:
if the board's occupant at `event.destination` isn't actually the piece
this event is about, that destination was overwritten by a later event
in the same batch, and there's nothing of this piece's own left here.

## GameEngine / view separation (2026-07-16)

`GameEngine` and `PieceSnapshot` carry only logical game facts:
`is_moving`, `is_jumping`, `rest_fraction_remaining`. They know nothing
about `AnimationState` or animation concepts - that enum now lives in
`view/animation_state.py`, and `derive_animation_state()` there is the
**only** place in the project that turns those logical facts into an
`AnimationState` (IDLE/MOVE/JUMP). `view/piece_state_machine.py` layers
the one-shot `LONG_REST`/`SHORT_REST` states on top of that using each
clip's own `next_state_when_finished` from `assets/piece_animations.py`
(read from `pieces2/<TOKEN>/states/<state>/config.json`), so the
transition chain (`move -> long_rest -> idle`, `jump -> short_rest ->
idle`, `idle -> idle`) isn't hardcoded in Python.

`PieceSnapshot.row/col` is a piece's *logical* cell - an in-flight piece
still reports its *source* here until it actually lands, so text
rendering (an integer grid) always has one definite cell to show it at.
`render_row/render_col` is the separate, continuously interpolated
visual position used for animation.

## Click routing across two players sharing one mouse (`view/click_router.py`)

A select-then-act gesture is always two clicks. The color of the piece
under the *first* click of a gesture owns every click until that
controller's own selection clears (successful move, illegal target, or
a first click that never selected anything) - after that the router is
free to route the next click by whatever's under it. With one mouse, a
click on an enemy piece while a gesture is active is indistinguishable
from "capture that piece", so it always completes the active gesture
rather than starting a new one for the other side.

## Stale selection safety (`input/controller.py`)

A selected piece can be captured (and its cell taken by someone else)
while waiting for a second click. `Controller._act_on_selection` cannot
tell this apart from "the same piece is still there" using `Position`
alone, so it confirms identity by piece id the same way
`RealTimeArbiter._resolve_arrival` does.

An illegal target always cancels the selection rather than leaving it
open for a retry - the piece must be reselected from scratch.

## wait(0) semantics

`GameEngine.wait(0)`/`RealTimeArbiter.advance_time(0)` never advances
the clock, but still resolves anything already due. `GameEngine`
construction rejects non-positive `move_duration`/`jump_duration`, so a
validated move always has `arrival_time` strictly in the future relative
to the queueing clock - it can never be immediately due. Combined with
`advance_time()` always fully draining whatever's overdue before it
returns, nothing can ever be left "due but unresolved" between calls.
This is why `Controller.click()`/`jump()` don't need their own
defensive `wait(0)` - though `ScriptRunner` still calls `wait(0)` before
every `print`, since a script can render at an arbitrary point in time.

## `Img.draw_on` alpha handling (`view/img.py`)

When blending a source image onto a target of a different channel count,
a 4-channel (BGRA) source drawn onto a 3-channel (BGR) target gets an
alpha channel added to the *target* (`COLOR_BGR2BGRA`), not stripped
from the source. Stripping the source's alpha instead would throw away
real transparency and paint whatever raw color sits under the
"transparent" pixels (often black) as fully opaque - this was a real
bug (solid black squares behind every piece sprite) traced to exactly
that mistake.

## Strategy-pattern extension points

- `rules/piece_rules.py` (`MovementStrategy`): a new `PieceKind`'s
  movement rule needs only an implementation registered with
  `PieceRuleRegistry` - no engine or parser changes.
- `engine/game_conditions.py` (`WinCondition`, `PromotionRule`):
  swappable so a variant (capture-the-flag, different promotion rules,
  etc.) can be plugged in without touching `GameEngine`.

## Asset folder naming (`assets/piece_animations.py`)

`token_to_folder` maps `(PieceColor, PieceKind)` to a `pieces2/` folder
name (e.g. `(WHITE, QUEEN) -> "QW"`) - **not** the same convention as
the engine's own board token (lowercase color + uppercase kind, e.g.
`"wQ"`). `pieces2/` folders are `<KIND><COLOR>`, both uppercase.
