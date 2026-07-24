# Architecture

A summary of the final design after the client/server refactor. For the
history of *why* each decision was made, see
[kf-chess-architecture-plan.md](kf-chess-architecture-plan.md) - this file
only describes what exists today.

## Layers

| Layer | Owns | Must not own |
|---|---|---|
| `model/` | Piece, Position, Board, GameState - plain data and board storage | any rule, timing, or rendering logic |
| `rules/` | legal-move validation per piece kind, win/promotion conditions | board storage, timing, sockets |
| `realtime/` | in-flight motions/jumps/rest, keyed off a millisecond clock the caller advances | rule validation, rendering, sockets |
| `engine/` | `GameEngine` - the single authority for one game: accepts/rejects moves and jumps, advances time, publishes domain events, produces snapshots | sockets, JSON, disconnect/rating bookkeeping |
| `events/` | `EventDispatcher` (pub/sub) and the event types; local subscribers (`ScoreTracker`, `ActionHistory`, `SoundSystem`) | networking - these are just other local subscribers |
| `protocol/` | the wire format: typed message classes, a type-tagged JSON registry, snapshot/event codecs | any decision about *when* to send something, or business rules |
| `server/` | one authoritative `GameEngine` per room, connections, matchmaking, ratings, one shared server loop | rendering, input handling |
| `client/` | login, lobby, a thin `GameWindow` that renders whatever the server says and forwards clicks as intents | any rule validation or authoritative game state |
| `view/` | cv2 rendering shared by every front end (local, text, networked) | sockets, rules, engine internals |
| `input/` | click/jump -> intent translation, shared by every front end | rendering, networking |

**Server authoritative, thin client.** The server holds the one real
`GameEngine` per room; the client never validates a move - it draws whatever
snapshot arrives and lets the server accept or reject each request.

## Client -> server message flow

```
mouse click / key
  -> input.Controller               (click/jump -> ActionSink call)
  -> client.ServerConnection        (typed MoveIntent/JumpIntent -> outbound queue)
  -> [wire: JSON, encode_json_message]
  -> server.ConnectionLifecycle      (decode_json_message once)
  -> server.ClientMessageRouter      (check participant.state, dispatch)
  -> server.GameSession.handle_move/handle_jump
  -> engine.GameEngine.request_move/request_jump
```

Ownership checks (does this connection own this piece?) happen in
`GameSession`, not `GameEngine` - a wrong-color attempt is unicast straight
back to the sender as an `IllegalActionEvent` and never reaches the engine.

Login and room/matchmaking intents (`Login`, `PlayIntent`, `RoomIntent`) take
the same decode -> route path but land in `Matchmaker` / `GameRoomRegistry`
instead of a `GameSession`.

## Server -> client snapshot/event flow

```
engine.GameEngine (state changes, or a tick advances time)
  -> events.EventDispatcher.publish(...)
  -> server.NetworkPublisher            (subscribed per room)
  -> server.GameRoomRegistry._broadcast_to_room / unicast
  -> [wire: JSON, message_to_payload / snapshot_to_payload]
  -> client.ServerConnection             (decode -> SnapshotReceived / EventReceived)
  -> client.GameWindow                   (drains inbound queue each frame)
  -> republishes onto a *local* EventDispatcher for ScoreTracker/ActionHistory/SoundSystem
  -> view.GameView.render(...)
```

`GameSnapshot` is broadcast once per server tick per active room (not per
event); domain events (`MoveCompletedEvent`, `CaptureEvent`, `GameOverEvent`,
...) are broadcast as they're published. `IllegalActionEvent` is the one
event that's always unicast, never broadcast.

## Server timing: one loop, tick-driven

Before this refactor, timing was split three ways: a per-room `asyncio` game
loop, a separate matchmaking-expiry poll loop, and a per-disconnect `asyncio`
task sleeping in real seconds. All three are gone. There is exactly one
`asyncio.sleep()` in the server (`server/ws_server.py`'s `_run_server_loop`),
and everything downstream is driven by `tick(dt_ms)` - a plain method call
with a measured elapsed-time argument, not a coroutine:

```
one real asyncio.sleep() per iteration
  -> measure actual elapsed time -> dt_ms
  -> matchmaker.tick(dt_ms)            -> expired waiters (no time.monotonic, no clock object)
  -> room_registry.tick(dt_ms)         for every active room, isolated:
       -> session.tick(dt_ms)
            -> engine.wait(dt_ms)                     (motions/jumps/rest advance)
            -> disconnect countdown advancement         (DisconnectCountdown state, no task/sleep)
       -> broadcast one snapshot for that room
  -> notify any matchmaking entries that just expired
```

Consequences of this design:

- **Matchmaker** has no clock dependency at all - `tick(dt_ms)` accumulates
  waited time on each queued entry itself, so its tests are synchronous and
  deterministic (no injected clock, no real sleeping).
- **Disconnect countdowns** are a small `DisconnectCountdown(remaining_ms,
  last_published_second)` value living on `GameSession`, advanced only by
  `tick(dt_ms)`. A `PlayerDisconnectedEvent` is published only when the
  *displayed* second actually changes, so a single large `dt_ms` (a slow
  tick, or a room that was idle) still lands on the right remaining second
  instead of needing one tick per second. Reconnecting removes the state
  outright - there is no task to cancel.
- **Room isolation**: `GameRoomRegistry.tick(dt_ms)` iterates a snapshot of
  its rooms; a room whose tick raises is logged and skipped, never allowed to
  stop any other room's tick or the server loop itself.
- **No more per-room tasks**: `server/game_loop.py` and the `Sleeper`
  Protocol are gone - there was nothing left for either to abstract once
  every tick call became synchronous.
