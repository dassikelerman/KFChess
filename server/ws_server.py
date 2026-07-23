"""Server entry point: wire every collaborator together and run the accept loop.

`python -m server.ws_server` is the whole server-side story in one file: build a
UserStore/RatingStore/GameRoomRegistry/Matchmaker/ClientMessageRouter, hand each new
WebSocket connection to a ConnectionLifecycle, and run the matchmaking-expiry timer
alongside it. Everything each of those classes actually decides is synchronous and
typed (see server/connection_lifecycle.py, server/router.py) - this file is only the
async wiring and the real websockets.serve() call.
"""

import asyncio
import json
import logging

import websockets

import constants
from logging_setup import configure_logging
from protocol.lobby_messages import MatchNotFound
from protocol.registry import message_to_payload
from server.connection_lifecycle import ConnectionLifecycle
from server.interfaces import MessageSender
from server.matchmaker import Matchmaker
from server.participant import ParticipantState
from server.rating import RatingStore
from server.rooms import GameRoomRegistry
from server.router import ClientMessageRouter
from server.user_store import UserStore

HOST = "localhost"
PORT = 8765
TICK_MS = constants.FRAME_POLL_MS
CLOSE_TIMEOUT_S = 3
EXPIRY_POLL_S = 1
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


async def _run_expiry_loop(matchmaker, send_fn: MessageSender):
    while True:
        await asyncio.sleep(EXPIRY_POLL_S)
        for expired in matchmaker.expire_waiting_entries():
            participant = expired.participant
            participant.state = ParticipantState.LOBBY
            send_fn(participant.connection, message_to_payload(MatchNotFound()))


async def main():
    configure_logging(constants.SERVER_LOG_PATH)
    user_store = UserStore()
    rating_store = RatingStore()
    game_room_registry = GameRoomRegistry(
        _unicast, rating_store, tick_ms=TICK_MS, disconnect_countdown_seconds=DISCONNECT_COUNTDOWN_SECONDS,
    )
    matchmaker = Matchmaker(expiry_seconds=MATCH_EXPIRY_S)
    router = ClientMessageRouter(game_room_registry, matchmaker)

    async def on_disconnect(participant):
        matchmaker.cancel_search(participant)
        await game_room_registry.remove_participant(participant)

    connection_lifecycle = ConnectionLifecycle(user_store, rating_store, router, on_disconnect)

    expiry_task = asyncio.create_task(_run_expiry_loop(matchmaker, _unicast))
    try:
        async with websockets.serve(connection_lifecycle.run, HOST, PORT, close_timeout=CLOSE_TIMEOUT_S):
            logger.info("KFChess server listening on ws://%s:%s", HOST, PORT)
            await asyncio.Future()
    finally:
        expiry_task.cancel()
        try:
            await expiry_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
