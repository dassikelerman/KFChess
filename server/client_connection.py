"""ClientConnection: recv/send/close for one raw websocket - nothing else.

A thin async wrapper local to ClientSession's login-then-message-loop story (see
server/client_session.py). It is the only thing in that story that imports websockets
or calls json.dumps - ClientSession only ever calls recv/send_payload/close on it, and
never sees a socket or a wire format. Participant.connection keeps holding the *raw*
websocket throughout, unwrapped - GameRoomRegistry, NetworkPublisher, and GameSession
key off of it directly as a plain identity and have no reason to know this wrapper
exists.
"""

import asyncio
import json

import websockets


class ClientConnection:
    def __init__(self, raw_connection):
        self._raw = raw_connection

    async def recv(self, timeout_s=None):
        try:
            if timeout_s is None:
                return await self._raw.recv()
            return await asyncio.wait_for(self._raw.recv(), timeout=timeout_s)
        except (asyncio.TimeoutError, websockets.ConnectionClosed):
            return None

    async def send_payload(self, payload):
        await self._raw.send(json.dumps(payload))

    async def close(self, code, reason):
        await self._raw.close(code=code, reason=reason)

    def __aiter__(self):
        return self._raw.__aiter__()
