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
import os
import queue
import ssl
import threading
from dataclasses import dataclass

import websockets

from protocol.game_messages import JumpIntent, MoveIntent
from protocol.lobby_messages import CreateRoomIntent, JoinRoomIntent, Login, PlayIntent
from protocol.message_types import MessageType
from protocol.registry import encode_json_message, message_from_payload
from protocol.snapshot_codec import CLOCK_MS_FIELD

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SnapshotReceived:
    game_snapshot: object
    clock_ms: int


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


def _dev_insecure_ssl_context(url):
    """Relax certificate verification for wss://, but only under an explicit dev
    opt-in - never by default. The local Caddy TLS-terminating proxy (see
    Server_Design.md's Load Balancer section) uses "tls internal", a cert signed
    by a local, non-public CA that the default context would reject outright. A
    real deployment's wss:// gets a real cert, so it must keep full verification -
    hence gating this on an env var instead of just detecting the wss:// scheme."""
    if not url.startswith("wss://") or os.environ.get("KFCHESS_DEV_INSECURE_TLS") != "1":
        return None
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


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

    def send_create_room_intent(self):
        self._outbound.put(CreateRoomIntent())

    def send_join_room_intent(self, join_code):
        self._outbound.put(JoinRoomIntent(join_code=join_code))

    def send_play_intent(self):
        self._outbound.put(PlayIntent())

    def _run(self):
        asyncio.run(self._connect_and_pump())

    async def _connect_and_pump(self):
        logger.info("connecting to %s", self._url)
        try:
            async with websockets.connect(self._url, ssl=_dev_insecure_ssl_context(self._url)) as connection:
                await self._run_receive_and_send(connection)
        except websockets.ConnectionClosed as e:
            reason = e.rcvd.reason if e.rcvd is not None else ""
            logger.info("connection closed: reason=%r", reason)
            self.inbound.put(ConnectionClosed(reason=reason))
        finally:
            # Guarantees the worker thread blocked in _send's Queue.get() wakes up no
            # matter which side ends the connection, or how - including _receive ending
            # with no exception at all, which is what a clean server-side close does.
            self._outbound.put(_CLOSE_SENTINEL)

    async def _run_receive_and_send(self, connection):
        # Not asyncio.gather(): gather() only returns early when one side *raises* - a
        # clean server-side close ends _receive's loop with no exception, so gather()
        # would then wait forever for _send too, which is itself blocked on the outbound
        # queue with nothing left to wake it. asyncio.wait(FIRST_COMPLETED) returns the
        # moment either side ends for any reason, and we cancel whichever is still going.
        receive_task = asyncio.create_task(self._receive(connection))
        send_task = asyncio.create_task(self._send(connection))
        done, pending = await asyncio.wait({receive_task, send_task}, return_when=asyncio.FIRST_COMPLETED)

        for task in pending:
            task.cancel()
        for task in pending:
            try:
                await task
            except asyncio.CancelledError:
                pass

        for task in done:
            task.result()  # re-raise whatever ended the pump, e.g. websockets.ConnectionClosed

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
            clock_ms = data.pop(CLOCK_MS_FIELD)
            game_snapshot = message_from_payload(data)
            self.inbound.put(SnapshotReceived(game_snapshot=game_snapshot, clock_ms=clock_ms))
        else:
            event = message_from_payload(data)
            self.inbound.put(EventReceived(event=event))
