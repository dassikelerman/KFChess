import asyncio
import json

import pytest

from protocol.lobby_messages import Login, RoomIntent
from protocol.message_types import RoomAction
from protocol.registry import message_to_payload
from server.connection_lifecycle import ClientMessageRouter, ConnectionLifecycle
from server.contracts import Participant, ParticipantState
from server.rating import RatingStore
from server.rooms import GameRoomRegistry
from server.matchmaker import Matchmaker
from server.user_store import UserStore


class FakeConnection:
    def __init__(self, incoming=()):
        self._incoming = list(incoming)
        self.sent = []
        self.closed = None
        self.send_should_fail = False

    async def recv(self):
        if self._incoming:
            return self._incoming.pop(0)
        await asyncio.Event().wait()

    async def send(self, data):
        if self.send_should_fail:
            raise RuntimeError("boom")
        self.sent.append(data)

    async def close(self, code=1000, reason=""):
        self.closed = (code, reason)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._incoming:
            raise StopAsyncIteration
        return self._incoming.pop(0)


class FakeGameRoomRegistry:
    def try_reconnect(self, participant):
        return None


class FakeMatchmaker:
    pass  # unused by the simple login-only scenarios below


def _login_message(username, password="hunter2"):
    return json.dumps(message_to_payload(Login(username=username, password=password)))


def _make_stores(tmp_path):
    db_path = str(tmp_path / "test_users.db")
    return UserStore(db_path), RatingStore(db_path)


def _make_lifecycle(user_store, rating_store):
    router = ClientMessageRouter(FakeGameRoomRegistry(), FakeMatchmaker())
    disconnect_calls = []

    async def on_disconnect(participant):
        disconnect_calls.append(participant)

    lifecycle = ConnectionLifecycle(user_store, rating_store, router, on_disconnect)
    return lifecycle, disconnect_calls


def test_a_successful_login_reaches_lobby_and_receives_logged_in(tmp_path):
    user_store, rating_store = _make_stores(tmp_path)
    lifecycle, disconnect_calls = _make_lifecycle(user_store, rating_store)
    connection = FakeConnection([_login_message("alice")])

    asyncio.run(lifecycle.run(connection))

    sent_types = [json.loads(payload)["type"] for payload in connection.sent]
    assert sent_types == ["LoggedIn"]
    assert connection.closed is None
    assert len(disconnect_calls) == 1
    participant = disconnect_calls[0]
    assert participant.username == "alice"
    assert participant.authenticated is True
    assert participant.state is ParticipantState.DISCONNECTED


def test_a_wrong_password_is_rejected_and_closed_without_reaching_the_lobby(tmp_path):
    user_store, rating_store = _make_stores(tmp_path)
    user_store.create_or_verify("alice", "correct-password")
    lifecycle, disconnect_calls = _make_lifecycle(user_store, rating_store)
    connection = FakeConnection([_login_message("alice", "wrong-password")])

    asyncio.run(lifecycle.run(connection))

    assert connection.sent == []
    assert connection.closed is not None
    assert len(disconnect_calls) == 1
    assert disconnect_calls[0].authenticated is False


def test_a_malformed_login_is_rejected_and_closed_without_reaching_the_lobby(tmp_path):
    user_store, rating_store = _make_stores(tmp_path)
    lifecycle, disconnect_calls = _make_lifecycle(user_store, rating_store)
    connection = FakeConnection(["not json {"])

    asyncio.run(lifecycle.run(connection))

    assert connection.sent == []
    assert connection.closed is not None
    assert len(disconnect_calls) == 1
    assert disconnect_calls[0].authenticated is False


def test_the_disconnect_callback_fires_exactly_once_even_when_an_error_occurs_mid_handling(tmp_path):
    user_store, rating_store = _make_stores(tmp_path)
    lifecycle, disconnect_calls = _make_lifecycle(user_store, rating_store)
    connection = FakeConnection([_login_message("alice")])
    connection.send_should_fail = True

    with pytest.raises(RuntimeError):
        asyncio.run(lifecycle.run(connection))

    assert len(disconnect_calls) == 1


def test_no_password_or_hash_or_salt_ever_appears_in_the_logs(tmp_path, caplog):
    user_store, rating_store = _make_stores(tmp_path)
    lifecycle, _ = _make_lifecycle(user_store, rating_store)
    connection = FakeConnection([_login_message("alice", "super-secret-password")])

    with caplog.at_level("DEBUG"):
        asyncio.run(lifecycle.run(connection))

    assert "super-secret-password" not in caplog.text


def test_no_password_appears_in_the_logs_even_on_a_wrong_password_rejection(tmp_path, caplog):
    user_store, rating_store = _make_stores(tmp_path)
    user_store.create_or_verify("alice", "correct-password")
    lifecycle, _ = _make_lifecycle(user_store, rating_store)
    connection = FakeConnection([_login_message("alice", "wrong-super-secret-password")])

    with caplog.at_level("DEBUG"):
        asyncio.run(lifecycle.run(connection))

    assert "wrong-super-secret-password" not in caplog.text
    assert "correct-password" not in caplog.text


# -- Part 4: real ROOM flow (real GameRoomRegistry + real ClientMessageRouter) ----


def _make_real_lifecycle(user_store, rating_store):
    sent = []

    def send_fn(connection, payload):
        sent.append((connection, payload))

    game_room_registry = GameRoomRegistry(send_fn, rating_store)
    router = ClientMessageRouter(game_room_registry, Matchmaker())
    disconnect_calls = []

    async def on_disconnect(participant):
        disconnect_calls.append(participant)
        await game_room_registry.remove_participant(participant)

    lifecycle = ConnectionLifecycle(user_store, rating_store, router, on_disconnect)
    return lifecycle, game_room_registry, disconnect_calls


def test_create_room_sequence_receives_room_created_then_role_then_snapshot_in_order(tmp_path):
    async def scenario():
        user_store, rating_store = _make_stores(tmp_path)
        lifecycle, _, _ = _make_real_lifecycle(user_store, rating_store)
        connection = FakeConnection([
            _login_message("alice"),
            json.dumps(message_to_payload(RoomIntent(action=RoomAction.CREATE))),
        ])

        await lifecycle.run(connection)

        sent_types = [json.loads(payload)["type"] for payload in connection.sent]
        assert sent_types == ["LoggedIn", "RoomCreated", "role", "GameSnapshot"]
        assert json.loads(connection.sent[2])["role"] == "white"

    asyncio.run(scenario())


def test_join_with_an_unknown_room_id_receives_room_rejected_and_stays_in_lobby(tmp_path):
    async def scenario():
        user_store, rating_store = _make_stores(tmp_path)
        lifecycle, _, disconnect_calls = _make_real_lifecycle(user_store, rating_store)
        connection = FakeConnection([
            _login_message("alice"),
            json.dumps(message_to_payload(RoomIntent(action=RoomAction.JOIN, room_id="no-such-room"))),
        ])

        await lifecycle.run(connection)

        sent_types = [json.loads(payload)["type"] for payload in connection.sent]
        assert sent_types == ["LoggedIn", "RoomRejected"]
        assert disconnect_calls[0].room_id is None
        assert disconnect_calls[0].role is None

    asyncio.run(scenario())


def test_a_second_client_joining_an_existing_room_gets_black_and_the_rooms_real_snapshot(tmp_path):
    async def scenario():
        user_store, rating_store = _make_stores(tmp_path)
        lifecycle, game_room_registry, _ = _make_real_lifecycle(user_store, rating_store)
        creator_client = Participant(connection="creator-conn")
        placement = game_room_registry.create_private_room(creator_client)

        second_connection = FakeConnection([
            _login_message("bob"),
            json.dumps(message_to_payload(RoomIntent(action=RoomAction.JOIN, room_id=placement.room_id))),
        ])

        await lifecycle.run(second_connection)

        sent_types = [json.loads(payload)["type"] for payload in second_connection.sent]
        assert sent_types == ["LoggedIn", "role", "GameSnapshot"]
        assert json.loads(second_connection.sent[1])["role"] == "black"

        expected_pieces = message_to_payload(placement.session.components.engine.snapshot())["pieces"]
        actual_pieces = json.loads(second_connection.sent[2])["pieces"]
        assert actual_pieces == expected_pieces

        await game_room_registry.remove_participant(creator_client)

    asyncio.run(scenario())
