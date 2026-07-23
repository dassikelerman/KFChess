import asyncio
import json

import server.connection_lifecycle as connection_lifecycle
from protocol.lobby_messages import Login
from protocol.registry import message_to_payload
from server.rating import RatingStore
from server.user_store import UserStore


class FakeConnection:
    """Stands in for a real websockets server connection - just enough of
    recv()/send()/close() plus async iteration for await_login to drive,
    without opening a real socket."""

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
    return json.dumps(message_to_payload(Login(username=username, password=password)))


def _run_await_login(raw_messages, user_store=None):
    if user_store is None:
        user_store = UserStore(":memory:")  # a real UserStore, just not file-backed
    connection = FakeConnection(raw_messages)

    async def scenario():
        return await connection_lifecycle.await_login(connection, user_store)

    username = asyncio.run(scenario())
    return connection, username, user_store


def test_decode_login_goes_through_the_shared_message_registry():
    # Proves the unification with decode_json_message rather than a separate hand-rolled
    # JSON parse: a raw wire string built the normal way (message_to_payload) decodes
    # into exactly the (username, password, no rejection) tuple await_login expects.
    username, password, reason = connection_lifecycle._decode_login(_login_message("alice"))

    assert (username, password, reason) == ("alice", "hunter2", None)


def test_valid_login_returns_the_username():
    connection, username, _ = _run_await_login([_login_message("alice")])

    assert username == "alice"
    assert connection.closed is None


def test_login_with_surrounding_whitespace_is_returned_trimmed():
    connection, username, _ = _run_await_login([_login_message("  alice  ")])

    assert username == "alice"


def test_malformed_json_is_rejected_and_closed():
    connection, username, _ = _run_await_login(["not json {"])

    assert username is None
    assert connection.closed is not None


def test_wrong_message_type_is_rejected_and_closed():
    raw = json.dumps({"type": "MoveIntent", "source": {"row": 0, "col": 0}, "destination": {"row": 0, "col": 1}})

    connection, username, _ = _run_await_login([raw])

    assert username is None
    assert connection.closed is not None


def test_missing_username_is_rejected_and_closed():
    raw = json.dumps({"type": "Login", "password": "hunter2"})

    connection, username, _ = _run_await_login([raw])

    assert username is None
    assert connection.closed is not None


def test_non_string_username_is_rejected_and_closed():
    raw = json.dumps({"type": "Login", "username": 123, "password": "hunter2"})

    connection, username, _ = _run_await_login([raw])

    assert username is None
    assert connection.closed is not None


def test_empty_or_whitespace_username_is_rejected_and_closed():
    raw = json.dumps({"type": "Login", "username": "   ", "password": "hunter2"})

    connection, username, _ = _run_await_login([raw])

    assert username is None
    assert connection.closed is not None


def test_a_connection_that_never_sends_anything_is_closed_after_the_timeout(monkeypatch):
    monkeypatch.setattr(connection_lifecycle, "LOGIN_TIMEOUT_S", 0.05)

    connection, username, _ = _run_await_login([])

    assert username is None
    assert connection.closed is not None


# -- Feature 4: password / user_store integration ----------------------------


def test_a_new_username_creates_an_account(tmp_path):
    db_path = str(tmp_path / "test_users.db")
    user_store = UserStore(db_path)

    connection, username, _ = _run_await_login([_login_message("alice", "hunter2")], user_store=user_store)

    assert username == "alice"
    assert connection.closed is None
    assert RatingStore(db_path).get_rating("alice") == 1200


def test_an_existing_user_with_the_correct_password_succeeds():
    user_store = UserStore(":memory:")
    user_store.create_or_verify("alice", "hunter2")  # account already exists

    connection, username, _ = _run_await_login([_login_message("alice", "hunter2")], user_store=user_store)

    assert username == "alice"
    assert connection.closed is None


def test_an_existing_user_with_the_wrong_password_is_rejected_and_closed():
    user_store = UserStore(":memory:")
    user_store.create_or_verify("alice", "correct-password")

    connection, username, _ = _run_await_login([_login_message("alice", "wrong-password")], user_store=user_store)

    assert username is None
    assert connection.closed is not None
