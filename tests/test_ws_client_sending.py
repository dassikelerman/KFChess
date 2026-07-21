import asyncio

import websockets
from websockets.frames import Close

from client.ws_client import WsClient
from events.serialization import JumpIntent, Login, MoveIntent, to_dict
from model.position import Position


def make_client():
    return WsClient("ws://unused")


def test_send_login_enqueues_a_serialized_login():
    client = make_client()

    client.send_login("alice", "hunter2")

    payload = client._outbound.get_nowait()
    assert payload == to_dict(Login(username="alice", password="hunter2"))


def test_request_move_enqueues_a_serialized_move_intent():
    client = make_client()

    client.request_move(Position(0, 0), Position(0, 2))

    payload = client._outbound.get_nowait()
    assert payload == to_dict(MoveIntent(source=Position(0, 0), destination=Position(0, 2)))


def test_request_jump_enqueues_a_serialized_jump_intent():
    client = make_client()

    client.request_jump(Position(1, 1))

    payload = client._outbound.get_nowait()
    assert payload == to_dict(JumpIntent(position=Position(1, 1)))


def test_multiple_outbound_intents_queue_in_order():
    client = make_client()

    client.request_move(Position(0, 0), Position(0, 1))
    client.request_jump(Position(2, 2))

    first = client._outbound.get_nowait()
    second = client._outbound.get_nowait()
    assert first["type"] == "MoveIntent"
    assert second["type"] == "JumpIntent"


def test_request_move_does_not_touch_the_inbound_queue():
    client = make_client()

    client.request_move(Position(0, 0), Position(0, 1))

    assert client.inbound.empty()


def test_request_jump_does_not_touch_the_inbound_queue():
    client = make_client()

    client.request_jump(Position(0, 0))

    assert client.inbound.empty()


def test_a_rejected_login_reports_closed_on_the_inbound_queue(monkeypatch):
    # server/ws_server.py rejects a bad login by closing the connection
    # with a reason (e.g. "wrong password") - _connect_and_pump must
    # report that as a "closed" inbound item, not just let the
    # background thread die silently, or client/run.py's initial wait
    # loop would hang forever on a connection that's already dead.
    client = make_client()

    class FakeConnection:
        async def __aenter__(self):
            close = Close(code=1008, reason="wrong password")
            raise websockets.ConnectionClosedError(rcvd=close, sent=None)

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(websockets, "connect", lambda url: FakeConnection())

    asyncio.run(client._connect_and_pump())

    assert client.inbound.get_nowait() == ("closed", "wrong password")
