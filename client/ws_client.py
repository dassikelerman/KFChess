"""Step 5 of the client/server migration (docs/kf-chess-architecture-plan.md):
a background thread with its own asyncio event loop, connecting to the
server and decoding every inbound message onto a thread-safe queue for
the main (cv2-owning) thread to drain each frame.

Also satisfies the ActionSink Protocol (input/controller.py):
request_move()/request_jump() are called from the main/render thread
and must not block it, so they only enqueue a serialized intent onto a
second, outbound queue - the background loop drains and sends it."""

import asyncio
import json
import queue
import threading

import websockets

from events.serialization import JumpIntent, Login, MoveIntent, from_dict, to_dict


class WsClient:
    def __init__(self, url):
        self._url = url
        self.inbound = queue.Queue()
        self._outbound = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    # -- main thread, non-blocking - each just enqueues onto _outbound ------

    def send_login(self, username):
        self._outbound.put(to_dict(Login(username=username)))

    # -- ActionSink Protocol (input/controller.py) ---------------------------

    def request_move(self, source, destination):
        self._outbound.put(to_dict(MoveIntent(source=source, destination=destination)))

    def request_jump(self, position):
        self._outbound.put(to_dict(JumpIntent(position=position)))

    # -- background thread ---------------------------------------------------

    def _run(self):
        asyncio.run(self._connect_and_pump())

    async def _connect_and_pump(self):
        async with websockets.connect(self._url) as connection:
            await asyncio.gather(self._receive(connection), self._send(connection))

    async def _receive(self, connection):
        async for raw in connection:
            self._handle_message(raw)

    async def _send(self, connection):
        loop = asyncio.get_event_loop()
        while True:
            # self._outbound is a plain (blocking) queue.Queue, shared
            # with the main thread - run_in_executor keeps that block off
            # this asyncio loop so _receive keeps running concurrently.
            payload = await loop.run_in_executor(None, self._outbound.get)
            await connection.send(json.dumps(payload))

    def _handle_message(self, raw):
        data = json.loads(raw)
        message_type = data.get("type")
        if message_type == "GameSnapshot":
            clock_ms = data.pop("clock_ms")
            game_snapshot = from_dict(data)
            self.inbound.put(("snapshot", game_snapshot, clock_ms))
        elif message_type == "role":
            # Not one of serialization.py's registered dataclasses - the
            # server's own seat-assignment message (server/ws_server.py),
            # sent once right after a successful login.
            self.inbound.put(("role", data["role"]))
        else:
            event = from_dict(data)
            self.inbound.put(("event", event))
