import asyncio
import json

import server.ws_server as ws_server
from protocol.serialization import Login, to_dict
from server.session import Session
from server.user_store import UserStore

BOARD = ["wK .", ". ."]


class FakeConnection:
    """Stands in for a real websockets server connection - just enough of
    recv()/send()/close() plus async iteration for _handle_connection to
    drive, without opening a real socket."""

    def __init__(self, incoming=()):
        self._incoming = list(incoming)
        self.sent = []
        self.closed = None

    async def recv(self):
        if self._incoming:
            return self._incoming.pop(0)
        # No message queued - hangs until asyncio.wait_for's timeout
        # cancels this await, the same way a real idle socket would.
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


def _login_message(username, password="hunter2"):
    return json.dumps(to_dict(Login(username=username, password=password)))


def _spy_session():
    session = Session(BOARD)
    assign_role_calls = []
    record_login_calls = []
    original_assign_role = session.assign_role
    original_record_login = session.record_login

    def spy_assign_role(connection):
        assign_role_calls.append(connection)
        return original_assign_role(connection)

    def spy_record_login(connection, username):
        record_login_calls.append((connection, username))
        return original_record_login(connection, username)

    session.assign_role = spy_assign_role
    session.record_login = spy_record_login
    return session, assign_role_calls, record_login_calls


def _run_handshake(raw_messages, user_store=None):
    if user_store is None:
        user_store = UserStore(":memory:")  # a real UserStore, just not file-backed
    connection = FakeConnection(raw_messages)
    session, assign_role_calls, record_login_calls = _spy_session()
    connections = set()

    async def scenario():
        await ws_server._handle_connection(
            connection, session, user_store, lambda: {"type": "GameSnapshot", "clock_ms": 0}, connections,
        )

    asyncio.run(scenario())
    return connection, assign_role_calls, record_login_calls, user_store


def test_valid_login_proceeds_to_role_assignment():
    connection, assign_role_calls, record_login_calls, _ = _run_handshake([_login_message("alice")])

    assert assign_role_calls == [connection]
    assert record_login_calls == [(connection, "alice")]
    assert connection.closed is None
    sent_types = [json.loads(payload)["type"] for payload in connection.sent]
    assert sent_types[0] == "role"


def test_login_with_surrounding_whitespace_is_stored_trimmed():
    connection, _, record_login_calls, _ = _run_handshake([_login_message("  alice  ")])

    assert record_login_calls == [(connection, "alice")]


def test_malformed_json_is_rejected_and_closed_without_assigning_a_role():
    connection, assign_role_calls, record_login_calls, _ = _run_handshake(["not json {"])

    assert assign_role_calls == []
    assert record_login_calls == []
    assert connection.closed is not None


def test_wrong_message_type_is_rejected_and_closed_without_assigning_a_role():
    raw = json.dumps({"type": "MoveIntent", "source": {"row": 0, "col": 0}, "destination": {"row": 0, "col": 1}})

    connection, assign_role_calls, record_login_calls, _ = _run_handshake([raw])

    assert assign_role_calls == []
    assert record_login_calls == []
    assert connection.closed is not None


def test_missing_username_is_rejected_and_closed_without_assigning_a_role():
    raw = json.dumps({"type": "Login", "password": "hunter2"})

    connection, assign_role_calls, record_login_calls, _ = _run_handshake([raw])

    assert assign_role_calls == []
    assert record_login_calls == []
    assert connection.closed is not None


def test_non_string_username_is_rejected_and_closed_without_assigning_a_role():
    raw = json.dumps({"type": "Login", "username": 123, "password": "hunter2"})

    connection, assign_role_calls, record_login_calls, _ = _run_handshake([raw])

    assert assign_role_calls == []
    assert record_login_calls == []
    assert connection.closed is not None


def test_empty_or_whitespace_username_is_rejected_and_closed_without_assigning_a_role():
    raw = json.dumps({"type": "Login", "username": "   ", "password": "hunter2"})

    connection, assign_role_calls, record_login_calls, _ = _run_handshake([raw])

    assert assign_role_calls == []
    assert record_login_calls == []
    assert connection.closed is not None


def test_a_connection_that_never_sends_anything_is_closed_after_the_timeout(monkeypatch):
    monkeypatch.setattr(ws_server, "LOGIN_TIMEOUT_S", 0.05)

    connection, assign_role_calls, record_login_calls, _ = _run_handshake([])

    assert assign_role_calls == []
    assert record_login_calls == []
    assert connection.closed is not None


# -- Feature 4: password / user_store integration ----------------------------


def test_a_new_username_creates_an_account_and_proceeds_to_role_assignment():
    connection, assign_role_calls, record_login_calls, user_store = _run_handshake(
        [_login_message("alice", "hunter2")],
    )

    assert assign_role_calls == [connection]
    assert record_login_calls == [(connection, "alice")]
    assert connection.closed is None
    assert user_store.get_rating("alice") == 1200


def test_an_existing_user_with_the_correct_password_proceeds_to_role_assignment():
    user_store = UserStore(":memory:")
    user_store.create_or_verify("alice", "hunter2")  # account already exists

    connection, assign_role_calls, record_login_calls, _ = _run_handshake(
        [_login_message("alice", "hunter2")], user_store=user_store,
    )

    assert assign_role_calls == [connection]
    assert record_login_calls == [(connection, "alice")]
    assert connection.closed is None


def test_an_existing_user_with_the_wrong_password_is_rejected_and_closed_without_assigning_a_role():
    user_store = UserStore(":memory:")
    user_store.create_or_verify("alice", "correct-password")

    connection, assign_role_calls, record_login_calls, _ = _run_handshake(
        [_login_message("alice", "wrong-password")], user_store=user_store,
    )

    assert assign_role_calls == []
    assert record_login_calls == []
    assert connection.closed is not None
