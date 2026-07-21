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

    def send_login(self, username, password):
        self._outbound.put(to_dict(Login(username=username, password=password)))

    def request_move(self, source, destination):
        self._outbound.put(to_dict(MoveIntent(source=source, destination=destination)))

    def request_jump(self, position):
        self._outbound.put(to_dict(JumpIntent(position=position)))

    def _run(self):
        asyncio.run(self._connect_and_pump())

    async def _connect_and_pump(self):
        try:
            async with websockets.connect(self._url) as connection:
                await asyncio.gather(self._receive(connection), self._send(connection))
        except websockets.ConnectionClosed as e:
            reason = e.rcvd.reason if e.rcvd is not None else ""
            self.inbound.put(("closed", reason))

    async def _receive(self, connection):
        async for raw in connection:
            self._handle_message(raw)

    async def _send(self, connection):
        loop = asyncio.get_event_loop()
        while True:
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
            self.inbound.put(("role", data["role"]))
        else:
            event = from_dict(data)
            self.inbound.put(("event", event))
