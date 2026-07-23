"""ServerConnection: the client's connection to the server - connect, send, receive.

The cv2 main loop must never block on the network, so the socket and its asyncio loop
live on a background thread. This class is the thread-safe bridge: the main thread
calls send_login/request_move/etc. and drains `inbound`; the background thread pumps
the WebSocket and decodes whatever arrives into the typed items on that queue. Both
queues carry typed messages, not dicts - `_outbound` holds the same Login/MoveIntent/...
objects the caller built, and encode_json_message only runs at the actual `connection.
send()` call, right at the network boundary. Neither thread ever touches the other's
internals directly - the two queues are the only handoff.
"""

import asyncio
import json
import logging
import queue
import threading
from dataclasses import dataclass

import websockets

from protocol.game_messages import JumpIntent, MoveIntent
from protocol.lobby_messages import Login, PlayIntent, RoomIntent
from protocol.message_types import MessageType
from protocol.registry import encode_json_message, message_from_payload

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SnapshotReceived:
    game_snapshot: object
    clock_ms: int


@dataclass(frozen=True)
class RoleAssigned:
    role: str


@dataclass(frozen=True)
class EventReceived:
    event: object


@dataclass(frozen=True)
class ConnectionClosed:
    reason: str


# The outbound queue is read by a worker thread blocked on a plain (non-timeout)
# Queue.get(), which is not a daemon thread - without an explicit item to wake it,
# it blocks forever and the process can never exit. This sentinel is that item.
_CLOSE_SENTINEL = object()


class ServerConnection:
    def __init__(self, url):
        self._url = url
        self.inbound = queue.Queue()
        self._outbound = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def close(self):
        self._outbound.put(_CLOSE_SENTINEL)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def send_login(self, username, password):
        logger.info("sending login for username=%r", username)  # never log the password itself
        self._outbound.put(Login(username=username, password=password))

    def request_move(self, source, destination):
        self._outbound.put(MoveIntent(source=source, destination=destination))

    def request_jump(self, position):
        self._outbound.put(JumpIntent(position=position))

    def send_room_intent(self, action, room_id=None):
        self._outbound.put(RoomIntent(action=action, room_id=room_id))

    def send_play_intent(self):
        self._outbound.put(PlayIntent())

    def _run(self):
        asyncio.run(self._connect_and_pump())

    async def _connect_and_pump(self):
        logger.info("connecting to %s", self._url)
        try:
            async with websockets.connect(self._url) as connection:
                await asyncio.gather(self._receive(connection), self._send(connection))
        except websockets.ConnectionClosed as e:
            reason = e.rcvd.reason if e.rcvd is not None else ""
            logger.info("connection closed: reason=%r", reason)
            self.inbound.put(ConnectionClosed(reason=reason))
        finally:
            # Guarantees the worker thread blocked in _send's Queue.get() wakes up
            # even when _receive is the side that ended the connection.
            self._outbound.put(_CLOSE_SENTINEL)

    async def _receive(self, connection):
        async for raw in connection:
            self._handle_message(raw)

    async def _send(self, connection):
        loop = asyncio.get_event_loop()
        while True:
            message = await loop.run_in_executor(None, self._outbound.get)
            if message is _CLOSE_SENTINEL:
                await connection.close()
                return
            await connection.send(encode_json_message(message))

    def _handle_message(self, raw):
        data = json.loads(raw)
        message_type = data.get("type")
        if message_type == MessageType.GAME_SNAPSHOT:
            clock_ms = data.pop("clock_ms")
            game_snapshot = message_from_payload(data)
            self.inbound.put(SnapshotReceived(game_snapshot=game_snapshot, clock_ms=clock_ms))
        elif message_type == MessageType.ROLE:
            self.inbound.put(RoleAssigned(role=data["role"]))
        else:
            event = message_from_payload(data)
            self.inbound.put(EventReceived(event=event))
