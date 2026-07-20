"""Step 4 of the client/server migration (docs/kf-chess-architecture-plan.md):
a background thread with its own asyncio event loop, connecting to the
server and decoding every inbound message onto a thread-safe queue for
the main (cv2-owning) thread to drain each frame. No outbound sending
yet - intents (MoveIntent/JumpIntent) are Step 5."""

import asyncio
import json
import queue
import threading

import websockets

from events.serialization import from_dict


class WsClient:
    def __init__(self, url):
        self._url = url
        self.inbound = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def _run(self):
        asyncio.run(self._listen())

    async def _listen(self):
        async with websockets.connect(self._url) as connection:
            async for raw in connection:
                self._handle_message(raw)

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
            # not acted on yet since Controller/ownership isn't wired in
            # until Step 5.
            self.inbound.put(("role", data["role"]))
        else:
            event = from_dict(data)
            self.inbound.put(("event", event))
