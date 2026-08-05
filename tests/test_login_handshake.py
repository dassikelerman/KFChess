import asyncio
import json

import server.client_session as client_session
from protocol.lobby_messages import Login
from protocol.registry import message_to_payload
from server.auth_service import AuthService
from server.client_connection import ClientConnection
from server.rating import RatingStore
from server.user_store import UserStore
from tests.db_helpers import reset_users_table


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


def _run_await_login(raw_messages, user_store=None, rating_store=None):
    if user_store is None:
        reset_users_table()
        user_store = UserStore()
    if rating_store is None:
        rating_store = RatingStore()
    auth_service = AuthService(user_store, rating_store)
    fake_connection = FakeConnection(raw_messages)
    connection = ClientConnection(fake_connection)

    async def scenario():
        return await client_session.await_login(connection, auth_service)

    identity = asyncio.run(scenario())
    return fake_connection, identity, user_store


def test_decode_login_goes_through_the_shared_message_registry():
    # Proves the unification with decode_json_message rather than a separate hand-rolled
    # JSON parse: a raw wire string built the normal way (message_to_payload) decodes
    # into exactly the (username, password, no rejection) tuple await_login expects.
    username, password, reason = client_session._decode_login(_login_message("alice"))

    assert (username, password, reason) == ("alice", "hunter2", None)


def test_valid_login_returns_the_identity():
    connection, identity, _ = _run_await_login([_login_message("alice")])

    assert identity.username == "alice"
    assert connection.closed is None


def test_login_with_surrounding_whitespace_is_returned_trimmed():
    connection, identity, _ = _run_await_login([_login_message("  alice  ")])

    assert identity.username == "alice"


def test_malformed_json_is_rejected_and_closed():
    connection, identity, _ = _run_await_login(["not json {"])

    assert identity is None
    assert connection.closed is not None


def test_wrong_message_type_is_rejected_and_closed():
    raw = json.dumps({"type": "MoveIntent", "source": {"row": 0, "col": 0}, "destination": {"row": 0, "col": 1}})

    connection, identity, _ = _run_await_login([raw])

    assert identity is None
    assert connection.closed is not None


def test_missing_username_is_rejected_and_closed():
    raw = json.dumps({"type": "Login", "password": "hunter2"})

    connection, identity, _ = _run_await_login([raw])

    assert identity is None
    assert connection.closed is not None


def test_non_string_username_is_rejected_and_closed():
    raw = json.dumps({"type": "Login", "username": 123, "password": "hunter2"})

    connection, identity, _ = _run_await_login([raw])

    assert identity is None
    assert connection.closed is not None


def test_empty_or_whitespace_username_is_rejected_and_closed():
    raw = json.dumps({"type": "Login", "username": "   ", "password": "hunter2"})

    connection, identity, _ = _run_await_login([raw])

    assert identity is None
    assert connection.closed is not None


def test_a_connection_that_never_sends_anything_is_closed_after_the_timeout(monkeypatch):
    monkeypatch.setattr(client_session, "LOGIN_TIMEOUT_S", 0.05)

    connection, identity, _ = _run_await_login([])

    assert identity is None
    assert connection.closed is not None


# -- Feature 4: password / user_store integration ----------------------------


def test_a_new_username_creates_an_account():
    reset_users_table()
    user_store = UserStore()

    connection, identity, _ = _run_await_login([_login_message("alice", "hunter2")], user_store=user_store)

    assert identity.username == "alice"
    assert connection.closed is None
    assert RatingStore().get_rating("alice") == 1200


def test_an_existing_user_with_the_correct_password_succeeds():
    reset_users_table()
    user_store = UserStore()
    user_store.create_or_verify("alice", "hunter2")  # account already exists

    connection, identity, _ = _run_await_login([_login_message("alice", "hunter2")], user_store=user_store)

    assert identity.username == "alice"
    assert connection.closed is None


def test_an_existing_user_with_the_wrong_password_is_rejected_and_closed():
    reset_users_table()
    user_store = UserStore()
    user_store.create_or_verify("alice", "correct-password")

    connection, identity, _ = _run_await_login([_login_message("alice", "wrong-password")], user_store=user_store)

    assert identity is None
    assert connection.closed is not None
