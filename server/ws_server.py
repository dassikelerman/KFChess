"""WebSocket entry point for the KFChess server - step 7 of the
client/server migration (docs/kf-chess-architecture-plan.md). Accepts
connections, assigns seats, ticks the engine, broadcasts state, routes
incoming client intents to the engine, and enforces color ownership
(server/session.py) - a rejection is unicast straight back to whichever
connection sent it, never broadcast. --dev-single-client opts a single
connection into controlling both colors, for manual testing without
opening two windows; off by default.

Run as a module from the project root: python -m server.ws_server
                                    or: python -m server.ws_server --dev-single-client
"""

import argparse
import asyncio
import json
import logging
import time

import websockets

import constants
from server.network_publisher import NetworkPublisher
from server.session import Session

HOST = "localhost"
PORT = 8765
TICK_MS = constants.FRAME_POLL_MS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _broadcast(connections, payload):
    if connections:
        websockets.broadcast(connections, json.dumps(payload))


def _unicast(connection, payload):
    # session.handle_client_message() (and NetworkPublisher.unicast())
    # call this synchronously - connection.send() is a coroutine, so it's
    # scheduled as a task on the loop this function is called from rather
    # than awaited directly here.
    asyncio.create_task(connection.send(json.dumps(payload)))


async def _handle_connection(connection, session, network_publisher, connections):
    connections.add(connection)
    role = session.assign_role(connection)
    logger.info("connection assigned role=%s (now %d connected)", role, len(connections))

    try:
        await connection.send(json.dumps({"type": "role", "role": role}))
        await connection.send(json.dumps(network_publisher.snapshot_payload(session.components)))

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
        logger.info("connection closed (role=%s, %d still connected)", role, len(connections))


async def _tick_loop(session, network_publisher, connections):
    interval = TICK_MS / 1000
    last_tick = time.perf_counter()
    while True:
        await asyncio.sleep(interval)
        now = time.perf_counter()
        dt_ms = round((now - last_tick) * 1000)
        last_tick = now

        session.tick(dt_ms)
        _broadcast(connections, network_publisher.snapshot_payload(session.components))


async def main(dev_single_client=False):
    session = Session(
        constants.STANDARD_START_BOARD, allow_single_client_both_colors=dev_single_client,
    )
    connections = set()
    network_publisher = NetworkPublisher(
        session.components.dispatcher, lambda payload: _broadcast(connections, payload), _unicast,
    )
    session.network_publisher = network_publisher

    async def handler(connection):
        await _handle_connection(connection, session, network_publisher, connections)

    async with websockets.serve(handler, HOST, PORT):
        logger.info("KFChess server listening on ws://%s:%s", HOST, PORT)
        await _tick_loop(session, network_publisher, connections)


def _parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dev-single-client", action="store_true",
        help="let one connection control both white and black - for manual testing "
             "without opening two windows. Off by default.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(main(dev_single_client=args.dev_single_client))
