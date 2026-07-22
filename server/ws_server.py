import asyncio
import json
import logging

import websockets

import constants
from protocol.serialization import snapshot_to_payload
from server.game_loop import run_game_loop
from server.network_publisher import NetworkPublisher
from server.session import Session
from server.user_store import UserStore

HOST = "localhost"
PORT = 8765
TICK_MS = constants.FRAME_POLL_MS
LOGIN_TIMEOUT_S = 5
_REJECTED_LOGIN_CLOSE_CODE = 1008

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _parse_login_message(raw):
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None, None, "expected a JSON Login message"

    if not isinstance(data, dict) or data.get("type") != "Login":
        return None, None, "expected a Login message"

    username = data.get("username")
    if not isinstance(username, str):
        return None, None, "username must be a string"
    username = username.strip()
    if not username:
        return None, None, "username must not be empty"

    password = data.get("password")
    if not isinstance(password, str):
        return None, None, "password must be a string"
    if not password:
        return None, None, "password must not be empty"

    return username, password, None


async def _await_login(connection, user_store):
    try:
        raw = await asyncio.wait_for(connection.recv(), timeout=LOGIN_TIMEOUT_S)
    except asyncio.TimeoutError:
        await connection.close(code=_REJECTED_LOGIN_CLOSE_CODE, reason="login timed out")
        return None
    except websockets.ConnectionClosed:
        return None

    username, password, rejection_reason = _parse_login_message(raw)
    if rejection_reason is not None:
        await connection.close(code=_REJECTED_LOGIN_CLOSE_CODE, reason=rejection_reason)
        return None

    if user_store.create_or_verify(username, password) == "wrong_password":
        await connection.close(code=_REJECTED_LOGIN_CLOSE_CODE, reason="wrong password")
        return None

    return username


def _broadcast(connections, payload):
    if connections:
        websockets.broadcast(connections, json.dumps(payload))


def _unicast(connection, payload):
    asyncio.create_task(connection.send(json.dumps(payload)))


async def _handle_connection(connection, session, user_store, build_current_snapshot_payload, connections):
    role = None
    try:
        username = await _await_login(connection, user_store)
        if username is None:
            return

        session.record_login(connection, username)
        connections.add(connection)
        role = session.assign_role(connection)
        logger.info(
            "connection logged in as %r, assigned role=%s (now %d connected)", username, role, len(connections),
        )

        await connection.send(json.dumps({"type": "role", "role": role}))
        await connection.send(json.dumps(build_current_snapshot_payload()))

        async for message in connection:
            try:
                session.handle_client_message(connection, json.loads(message))
            except Exception:
                logger.exception("failed to handle message (role=%s): %s", role, message)
    finally:
        connections.discard(connection)
        session.disconnect(connection)
        logger.info("connection closed (role=%s, %d still connected)", role, len(connections))


async def main():
    user_store = UserStore()
    session = Session(constants.STANDARD_START_BOARD, user_store=user_store)
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
        await _handle_connection(connection, session, user_store, build_current_snapshot_payload, connections)

    def broadcast_snapshot():
        _broadcast(connections, build_current_snapshot_payload())

    async with websockets.serve(handler, HOST, PORT):
        logger.info("KFChess server listening on ws://%s:%s", HOST, PORT)
        await run_game_loop(session, broadcast_snapshot, TICK_MS)


if __name__ == "__main__":
    asyncio.run(main())
