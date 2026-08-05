"""Server entry point: wire every collaborator together and run the accept loop.

`python -m server.ws_server` is the whole server-side story in one file: build a
UserStore/RatingStore/AuthService/GameRoomRegistry/Matchmaker/ClientMessageRouter/
ParticipantLifecycle, hand each new WebSocket connection to a ClientSession, and run the
one global server loop alongside it - matchmaking expiry and every room's game tick
share this single asyncio.sleep(), there is no per-room task and no separate expiry
task. Everything each of those classes actually decides is synchronous and typed (see
server/client_session.py) - this file is only the async wiring, the real
websockets.serve() call, and the loop that measures elapsed time and ticks everything.
"""

import asyncio
import json
import logging
import time

import websockets

import constants
from logging_setup import configure_logging
from protocol.lobby_messages import MatchNotFound
from protocol.registry import message_to_payload
from server.auth_service import AuthService
from server.client_message_router import ClientMessageRouter
from server.client_session import ClientSession
from server.contracts import MessageSender, ParticipantState
from server.matchmaker import Matchmaker
from server.participant_lifecycle import ParticipantLifecycle
from server.rating import RatingStore
from server.rooms import GameRoomRegistry
from server.user_store import UserStore

HOST = "localhost"
PORT = 8765
SERVER_TICK_MS = constants.FRAME_POLL_MS
CLOSE_TIMEOUT_S = 3
MATCH_EXPIRY_S = constants.MATCHMAKING_TIMEOUT_SECONDS
DISCONNECT_COUNTDOWN_SECONDS = constants.DISCONNECT_COUNTDOWN_SECONDS

logger = logging.getLogger(__name__)


def _unicast(connection, payload):
    async def _send():
        try:
            await connection.send(json.dumps(payload))
        except websockets.ConnectionClosed:
            pass

    asyncio.create_task(_send())


async def _run_server_loop(matchmaker, room_registry, send_fn: MessageSender):
    interval = SERVER_TICK_MS / 1000
    last_tick = time.perf_counter()
    while True:
        await asyncio.sleep(interval)
        now = time.perf_counter()
        dt_ms = max(0, round((now - last_tick) * 1000))
        last_tick = now

        expired_matches = matchmaker.tick(dt_ms)
        room_registry.tick(dt_ms)
        for expired in expired_matches:
            participant = expired.participant
            participant.state = ParticipantState.LOBBY
            send_fn(participant.connection, message_to_payload(MatchNotFound()))


async def main():
    configure_logging(constants.SERVER_LOG_PATH)
    user_store = UserStore()
    rating_store = RatingStore()
    auth_service = AuthService(user_store, rating_store)
    room_registry = GameRoomRegistry(_unicast, rating_store, disconnect_countdown_seconds=DISCONNECT_COUNTDOWN_SECONDS)
    matchmaker = Matchmaker(expiry_seconds=MATCH_EXPIRY_S)
    router = ClientMessageRouter(room_registry, matchmaker)
    participant_lifecycle = ParticipantLifecycle(matchmaker, room_registry)

    client_session = ClientSession(auth_service, router, participant_lifecycle.leave)

    server_loop_task = asyncio.create_task(_run_server_loop(matchmaker, room_registry, _unicast))
    try:
        async with websockets.serve(client_session.run, HOST, PORT, close_timeout=CLOSE_TIMEOUT_S):
            logger.info("KFChess server listening on ws://%s:%s", HOST, PORT)
            await asyncio.Future()
    finally:
        server_loop_task.cancel()
        try:
            await server_loop_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
