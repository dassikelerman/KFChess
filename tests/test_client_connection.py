import asyncio
import json

import websockets

from server.client_connection import ClientConnection


class FakeRawConnection:
    def __init__(self, incoming=(), raise_closed_on_recv=False):
        self._incoming = list(incoming)
        self._raise_closed_on_recv = raise_closed_on_recv
        self.sent = []
        self.closed = None

    async def recv(self):
        if self._raise_closed_on_recv:
            raise websockets.ConnectionClosed(None, None)
        if self._incoming:
            return self._incoming.pop(0)
        await asyncio.Event().wait()

    async def send(self, data):
        self.sent.append(data)

    async def close(self, code=1000, reason=""):
        self.closed = (code, reason)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._incoming:
            raise StopAsyncIteration
        return self._incoming.pop(0)


def test_recv_with_no_timeout_returns_the_next_message():
    raw = FakeRawConnection(["hello"])
    connection = ClientConnection(raw)

    result = asyncio.run(connection.recv())

    assert result == "hello"


def test_recv_with_a_timeout_returns_none_and_does_not_close_when_a_message_arrives_in_time():
    raw = FakeRawConnection(["hello"])
    connection = ClientConnection(raw)

    result = asyncio.run(connection.recv(timeout_s=5))

    assert result == "hello"
    assert raw.closed is None


def test_recv_with_a_timeout_returns_none_when_nothing_arrives_in_time():
    raw = FakeRawConnection([])
    connection = ClientConnection(raw)

    result = asyncio.run(connection.recv(timeout_s=0.05))

    assert result is None


def test_recv_returns_none_when_the_underlying_connection_is_already_closed():
    raw = FakeRawConnection(raise_closed_on_recv=True)
    connection = ClientConnection(raw)

    result = asyncio.run(connection.recv(timeout_s=5))

    assert result is None


def test_send_payload_json_encodes_the_dict_onto_the_raw_connection():
    raw = FakeRawConnection()
    connection = ClientConnection(raw)

    asyncio.run(connection.send_payload({"type": "LoggedIn", "username": "alice"}))

    assert raw.sent == [json.dumps({"type": "LoggedIn", "username": "alice"})]


def test_close_forwards_the_code_and_reason_to_the_raw_connection():
    raw = FakeRawConnection()
    connection = ClientConnection(raw)

    asyncio.run(connection.close(1008, "login timed out"))

    assert raw.closed == (1008, "login timed out")


def test_async_iteration_delegates_to_the_raw_connections_own_iteration():
    raw = FakeRawConnection(["one", "two"])
    connection = ClientConnection(raw)

    async def scenario():
        return [raw async for raw in connection]

    assert asyncio.run(scenario()) == ["one", "two"]
