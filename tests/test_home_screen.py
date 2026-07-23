from client.home_screen import connect_and_login, login, prompt_for_username
from client.server_connection import ConnectionClosed, EventReceived
from protocol.lobby_messages import LoggedIn


def _reader(*answers):
    values = iter(answers)
    return lambda prompt: next(values)


def test_prompt_for_username_reprompts_until_a_non_blank_answer():
    read_line = _reader("", "   ", "alice")

    assert prompt_for_username(read_line) == "alice"


def test_login_returns_on_the_first_successful_attempt():
    attempts = []

    def fake_attempt_login(ws_url, username, password):
        attempts.append((ws_url, username, password))
        return ("fake-connection", username, 1200)

    notifications = []
    result = login(
        "ws://server", read_line=_reader("alice"), read_secret=_reader("hunter2"),
        notify=notifications.append, attempt_login=fake_attempt_login,
    )

    assert result == ("fake-connection", "alice", 1200)
    assert attempts == [("ws://server", "alice", "hunter2")]
    assert notifications == []


def test_login_retries_with_the_same_username_after_a_rejected_password():
    attempts = []

    def fake_attempt_login(ws_url, username, password):
        attempts.append((username, password))
        return None if len(attempts) == 1 else (f"connection-{username}", username, 1400)

    notifications = []
    result = login(
        "ws://server", read_line=_reader("alice"), read_secret=_reader("wrong", "right"),
        notify=notifications.append, attempt_login=fake_attempt_login,
    )

    assert result == ("connection-alice", "alice", 1400)
    assert attempts == [("alice", "wrong"), ("alice", "right")]
    assert notifications == ["login failed"]


class _FakeServerConnection:
    def __init__(self, url):
        self.url = url
        self.started = False
        self.sent_login = None
        self.inbound = None  # set by the test before connect_and_login drains it

    def start(self):
        self.started = True

    def send_login(self, username, password):
        self.sent_login = (username, password)


def _queue_with(*items):
    import queue as queue_module

    q = queue_module.Queue()
    for item in items:
        q.put(item)
    return q


def test_connect_and_login_returns_the_client_username_and_rating_on_success():
    created = {}

    def factory(url):
        connection = _FakeServerConnection(url)
        connection.inbound = _queue_with(EventReceived(LoggedIn(username="alice", rating=1300)))
        created["connection"] = connection
        return connection

    result = connect_and_login("ws://server", "alice", "hunter2", connection_factory=factory)

    assert result == (created["connection"], "alice", 1300)
    assert created["connection"].started is True
    assert created["connection"].sent_login == ("alice", "hunter2")


def test_connect_and_login_returns_none_when_the_connection_closes_before_a_login_reply():
    def factory(url):
        connection = _FakeServerConnection(url)
        connection.inbound = _queue_with(ConnectionClosed(reason="wrong password"))
        return connection

    result = connect_and_login("ws://server", "alice", "hunter2", connection_factory=factory)

    assert result is None


def test_connect_and_login_skips_unrelated_inbound_items_before_the_login_reply():
    # A stray event arriving before LoggedIn (e.g. one queued from a previous attempt on
    # a reused connection) must not be mistaken for the login outcome.
    def factory(url):
        connection = _FakeServerConnection(url)
        connection.inbound = _queue_with(
            EventReceived(object()), EventReceived(LoggedIn(username="bob", rating=1100)),
        )
        return connection

    result = connect_and_login("ws://server", "bob", "hunter2", connection_factory=factory)

    assert result[1:] == ("bob", 1100)
