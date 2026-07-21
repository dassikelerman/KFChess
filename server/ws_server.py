"""WebSocket entry point for the KFChess server - step 6 of the
client/server migration (docs/kf-chess-architecture-plan.md). Accepts
connections, assigns seats, ticks the engine, broadcasts state, routes
incoming client intents to the engine, and enforces color ownership
(server/session.py) - a rejection is unicast straight back to whichever
connection sent it, never broadcast.

Feature 3 (docs/kf-chess-architecture-plan.md): before any of that, a
connection must log in - exactly one incoming message is awaited, with
a timeout, and it must be a valid Login (a non-empty username after
stripping); anything else (timeout, malformed JSON, wrong message
type, missing/non-string/empty username) closes the connection with a
reason and never reaches assign_role/session.record_login.

Run as a module from the project root: python -m server.ws_server
"""

import asyncio
import json
import logging

import websockets

import constants
from events.serialization import snapshot_to_payload
from server.game_loop import run_game_loop
from server.network_publisher import NetworkPublisher
from server.session import Session

HOST = "localhost"
PORT = 8765
TICK_MS = constants.FRAME_POLL_MS
LOGIN_TIMEOUT_S = 5
_REJECTED_LOGIN_CLOSE_CODE = 1008  # policy violation

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _parse_login_message(raw):
    """Returns (username, None) for a valid Login, or (None, reason) if
    the message should be rejected - kept as a plain function (no
    connection/asyncio involved) so the validation rules are testable
    on their own."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None, "expected a JSON Login message"

    if not isinstance(data, dict) or data.get("type") != "Login":
        return None, "expected a Login message"

    username = data.get("username")
    if not isinstance(username, str):
        return None, "username must be a string"

    username = username.strip()
    if not username:
        return None, "username must not be empty"

    return username, None


async def _await_login(connection):
    """Waits for exactly one incoming message and validates it as a
    Login. Returns the stripped username on success; on any failure it
    closes the connection with a reason and returns None - the caller
    must not proceed to session.record_login/assign_role."""
    try:
        raw = await asyncio.wait_for(connection.recv(), timeout=LOGIN_TIMEOUT_S)
    except asyncio.TimeoutError:
        await connection.close(code=_REJECTED_LOGIN_CLOSE_CODE, reason="login timed out")
        return None
    except websockets.ConnectionClosed:
        return None

    username, rejection_reason = _parse_login_message(raw)
    if rejection_reason is not None:
        await connection.close(code=_REJECTED_LOGIN_CLOSE_CODE, reason=rejection_reason)
        return None
    return username


def _broadcast(connections, payload):
    if connections:
        websockets.broadcast(connections, json.dumps(payload))


def _unicast(connection, payload):
    # session.handle_client_message() (and NetworkPublisher.unicast())
    # call this synchronously - connection.send() is a coroutine, so it's
    # scheduled as a task on the loop this function is called from rather
    # than awaited directly here.
    asyncio.create_task(connection.send(json.dumps(payload)))


async def _handle_connection(connection, session, build_current_snapshot_payload, connections):
    role = None
    try:
        username = await _await_login(connection)
        if username is None:
            return  # already rejected and closed by _await_login

        session.record_login(connection, username)
        connections.add(connection)
        role = session.assign_role(connection)
        logger.info("connection logged in as %r, assigned role=%s (now %d connected)", username, role, len(connections))

        await connection.send(json.dumps({"type": "role", "role": role}))
        await connection.send(json.dumps(build_current_snapshot_payload()))

        async for message in connection:
            try:
                session.handle_client_message(connection, json.loads(message))
            except Exception:
                # A malformed/undecodable message shouldn't take down this
                # connection or the tick loop over one bad message - log
                # and move on.
                logger.exception("failed to handle message (role=%s): %s", role, message)
    finally:
        connections.discard(connection)
        session.disconnect(connection)
        logger.info("connection closed (role=%s, %d still connected)", role, len(connections))


async def main():
    session = Session(constants.STANDARD_START_BOARD)
    connections = set()

    def broadcast_payload(payload):
        _broadcast(connections, payload)

    network_publisher = NetworkPublisher(session.components.dispatcher, broadcast_payload, _unicast)
    session.network_publisher = network_publisher

    def build_current_snapshot_payload():
        snapshot = session.components.engine.snapshot()
        clock_ms = session.components.engine.clock
        return snapshot_to_payload(snapshot, clock_ms)

    async def handler(connection):
        await _handle_connection(connection, session, build_current_snapshot_payload, connections)

    def broadcast_snapshot():
        _broadcast(connections, build_current_snapshot_payload())

    async with websockets.serve(handler, HOST, PORT):
        logger.info("KFChess server listening on ws://%s:%s", HOST, PORT)
        await run_game_loop(session, broadcast_snapshot, TICK_MS)


if __name__ == "__main__":
    asyncio.run(main())
