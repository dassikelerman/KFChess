# KungFu Chess

A real-time variant of chess: moves and jumps resolve after a delay instead of
instantly, and a "jump" onto a square can intercept an incoming enemy move.
Play locally in one process, or connect multiple clients to a WebSocket
server for real matches with matchmaking, private rooms, reconnection, and
ELO ratings.

See [docs/architecture.md](docs/architecture.md) for how the pieces fit
together - layers, message flow, and the server's timing model.

## Project layout

```
model/       Piece, Position, Board, GameState - core data, no rules baked in
rules/       PieceRuleRegistry + per-piece MovementStrategy, win/promotion conditions
realtime/    RealTimeArbiter - tracks in-flight motions/jumps/rest against a clock
engine/      GameEngine - turn orchestration on top of board+rules+arbiter+realtime
board_io/    parse board text into a Board, print a Board back to text
events/      EventDispatcher (pub/sub) + the game's event types + local subscribers
             (ScoreTracker, ActionHistory, SoundSystem)
app/         build_game(board_text) - wires one GameComponents bundle (engine+board+dispatcher)
input/       Controller + build_controller() - click/jump handling shared by every
             front end (local view, text mode, networked client)
view/        cv2 rendering: GameView, animations, and view/theme.py (named colors/sizes)
text/        a terminal-only front end, driven by a script file instead of clicks
protocol/    the wire format - typed messages, a type-tagged JSON registry, snapshot
             and event codecs (see docs/architecture.md for the full message list)
server/      the authoritative WebSocket server - see docs/architecture.md
client/      the networked GUI client - login, lobby, then GameWindow
scripts/     small manual smoke-test scripts (not part of the pytest suite)
tests/       pytest suite - one test file per module, plus *_end_to_end.py for
             full client<->server scenarios over a real socket
```

`view/run.py` is a local, no-network route through the same engine (handy for
quick manual testing); `client/run.py` is the networked client and does not
replace it.

## Installing

Requires Python 3.10+. From the repository root:

```
pip install -e ".[client,server,dev]"
```

This is an editable install, so code changes take effect immediately with no
`sys.path` hacks needed. Install only what you need instead of everything:

- `.[client]` - opencv-python + websockets, for running the GUI client
- `.[server]` - websockets + psycopg2-binary + redis, for running the server
- `.[dev]` - pytest + pytest-cov, for running the test suite

## Database

Accounts and ratings live in PostgreSQL (`server/user_store.py`,
`server/rating.py`), not a local file. Room/user/join-code routing metadata
lives in Redis (`server/room_directory.py`) - never the live game state
itself, which stays in process memory (see Server_Design.md's Redis
section). `docker compose up -d` also brings up a local Caddy container
that terminates TLS in front of the server (see "TLS" below). Start all
three before running the server or the test suite:

```
docker compose up -d
```

This matches the connection strings both default to
(`postgresql://kfchess:kfchess@localhost:5432/kfchess` and
`redis://localhost:6379/0`); override them with the `KFCHESS_DATABASE_URL`
and `KFCHESS_REDIS_URL` environment variables if you're pointing at
different instances.

## TLS

`ws_server` itself still only speaks plain `ws://` - the `tls_proxy`
service in `docker-compose.yml` (Caddy) is what terminates TLS, on
`wss://localhost:8443`, proxying through to the server on the host. It
uses Caddy's own local, non-public CA (`tls internal`), so a client
connecting through it must opt in to trusting that dev-only cert
explicitly via `KFCHESS_DEV_INSECURE_TLS=1` - see Server_Design.md's Load
Balancer section for why this doesn't relax anything for a real deployment
with a real certificate.

**Known caveat:** if your Python install has `pip_system_certs` (or
anything else that globally replaces `ssl.SSLContext`, e.g. via a `.pth`
file) active, it re-verifies every TLS connection against the OS trust
store regardless of `verify_mode`/`check_hostname`, which defeats
`KFCHESS_DEV_INSECURE_TLS` - the fix on such a machine is to trust Caddy's
local CA in the OS trust store directly, not a code change here.

## Running

```
python -m server.ws_server                                            # start the server (ws://localhost:8765)
python -m client.run ws://localhost:8765                              # direct client, bypassing the proxy
KFCHESS_DEV_INSECURE_TLS=1 python -m client.run wss://localhost:8443   # client via the local TLS proxy
python -m view.run                                                    # local, no-network single-process game
```

## Running tests

```
docker compose up -d   # most of the suite needs the real Postgres and Redis instances
pytest
```

Coverage is configured in `pyproject.toml` (`pytest --cov` for a report); run
`pytest --cov` to see it. There's no 100%-coverage gate - the threshold is set
a bit below the measured baseline so it stays meaningful without being a
tripwire on every small change.
