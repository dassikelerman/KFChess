import asyncio

import websockets
from websockets.frames import Close

from client.server_connection import ConnectionClosed, ServerConnection
from protocol.game_messages import JumpIntent, MoveIntent
from protocol.lobby_messages import Login
from model.position import Position


def make_client():
    return ServerConnection("ws://unused")


def test_send_login_enqueues_the_typed_login_not_a_dict():
    client = make_client()

    client.send_login("alice", "hunter2")

    message = client._outbound.get_nowait()
    assert message == Login(username="alice", password="hunter2")


def test_request_move_enqueues_the_typed_move_intent_not_a_dict():
    client = make_client()

    client.request_move(Position(0, 0), Position(0, 2))

    message = client._outbound.get_nowait()
    assert message == MoveIntent(source=Position(0, 0), destination=Position(0, 2))


def test_request_jump_enqueues_the_typed_jump_intent_not_a_dict():
    client = make_client()

    client.request_jump(Position(1, 1))

    message = client._outbound.get_nowait()
    assert message == JumpIntent(position=Position(1, 1))


def test_multiple_outbound_intents_queue_in_order():
    client = make_client()

    client.request_move(Position(0, 0), Position(0, 1))
    client.request_jump(Position(2, 2))

    first = client._outbound.get_nowait()
    second = client._outbound.get_nowait()
    assert isinstance(first, MoveIntent)
    assert isinstance(second, JumpIntent)


def test_request_move_does_not_touch_the_inbound_queue():
    client = make_client()

    client.request_move(Position(0, 0), Position(0, 1))

    assert client.inbound.empty()


def test_request_jump_does_not_touch_the_inbound_queue():
    client = make_client()

    client.request_jump(Position(0, 0))

    assert client.inbound.empty()


def test_send_login_never_logs_the_password(caplog):
    client = make_client()

    with caplog.at_level("DEBUG"):
        client.send_login("alice", "super-secret-password")

    assert "super-secret-password" not in caplog.text
    assert "alice" in caplog.text


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

    assert client.inbound.get_nowait() == ConnectionClosed(reason="wrong password")
