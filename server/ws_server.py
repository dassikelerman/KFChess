"""WebSocket entry point for the KFChess server - step 3 of the
client/server migration (docs/kf-chess-architecture-plan.md). Accepts
connections, assigns seats, ticks the engine, and broadcasts state.
No move/jump handling and no ownership enforcement yet - later steps.

Run as a module from the project root: python -m server.ws_server
"""

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


async def _handle_connection(connection, session, network_publisher, connections):
    connections.add(connection)
    role = session.assign_role(connection)
    logger.info("connection assigned role=%s (now %d connected)", role, len(connections))

    try:
        await connection.send(json.dumps({"type": "role", "role": role}))
        await connection.send(json.dumps(network_publisher.snapshot_payload(session.components)))

        async for message in connection:
            # Move/jump handling is a later step - for now, just observe
            # what clients send.
            logger.info("received message (role=%s): %s", role, message)
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


async def main():
    session = Session(constants.STANDARD_START_BOARD)
    connections = set()
    network_publisher = NetworkPublisher(
        session.components.dispatcher, lambda payload: _broadcast(connections, payload),
    )

    async def handler(connection):
        await _handle_connection(connection, session, network_publisher, connections)

    async with websockets.serve(handler, HOST, PORT):
        logger.info("KFChess server listening on ws://%s:%s", HOST, PORT)
        await _tick_loop(session, network_publisher, connections)


if __name__ == "__main__":
    asyncio.run(main())
