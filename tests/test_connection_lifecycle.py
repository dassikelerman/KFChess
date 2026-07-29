import asyncio
import json

import pytest

from protocol.lobby_messages import CreateRoomIntent, JoinRoomIntent, Login
from protocol.registry import message_to_payload
from server.api_gateway.auth import AuthGateway
from server.client_message_router import ClientMessageRouter
from server.connection_lifecycle import ConnectionLifecycle
from server.contracts import Participant, ParticipantState
from server.rating import RatingStore
from server.room_directory import RoomDirectory
from server.rooms import GameRoomRegistry
from server.matchmaker import Matchmaker
from server.user_store import UserStore
from server.ws_gateway.connection_handler import ConnectionHandler
from tests.db_helpers import reset_users_table
from tests.redis_helpers import flush_directory


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


def _make_stores():
    reset_users_table()
    return UserStore(), RatingStore()


def _make_lifecycle(user_store, rating_store):
    router = ClientMessageRouter(FakeGameRoomRegistry(), FakeMatchmaker())
    disconnect_calls = []

    async def on_disconnect(participant):
        disconnect_calls.append(participant)

    auth_gateway = AuthGateway(user_store)
    connection_handler = ConnectionHandler(rating_store, router)
    lifecycle = ConnectionLifecycle(auth_gateway, connection_handler, on_disconnect)
    return lifecycle, disconnect_calls


def test_a_successful_login_reaches_lobby_and_receives_logged_in():
    user_store, rating_store = _make_stores()
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


def test_a_wrong_password_is_rejected_and_closed_without_reaching_the_lobby():
    user_store, rating_store = _make_stores()
    user_store.create_or_verify("alice", "correct-password")
    lifecycle, disconnect_calls = _make_lifecycle(user_store, rating_store)
    connection = FakeConnection([_login_message("alice", "wrong-password")])

    asyncio.run(lifecycle.run(connection))

    assert connection.sent == []
    assert connection.closed is not None
    assert len(disconnect_calls) == 1
    assert disconnect_calls[0].authenticated is False


def test_a_malformed_login_is_rejected_and_closed_without_reaching_the_lobby():
    user_store, rating_store = _make_stores()
    lifecycle, disconnect_calls = _make_lifecycle(user_store, rating_store)
    connection = FakeConnection(["not json {"])

    asyncio.run(lifecycle.run(connection))

    assert connection.sent == []
    assert connection.closed is not None
    assert len(disconnect_calls) == 1
    assert disconnect_calls[0].authenticated is False


def test_the_disconnect_callback_fires_exactly_once_even_when_an_error_occurs_mid_handling():
    user_store, rating_store = _make_stores()
    lifecycle, disconnect_calls = _make_lifecycle(user_store, rating_store)
    connection = FakeConnection([_login_message("alice")])
    connection.send_should_fail = True

    with pytest.raises(RuntimeError):
        asyncio.run(lifecycle.run(connection))

    assert len(disconnect_calls) == 1


def test_no_password_or_hash_or_salt_ever_appears_in_the_logs(caplog):
    user_store, rating_store = _make_stores()
    lifecycle, _ = _make_lifecycle(user_store, rating_store)
    connection = FakeConnection([_login_message("alice", "super-secret-password")])

    with caplog.at_level("DEBUG"):
        asyncio.run(lifecycle.run(connection))

    assert "super-secret-password" not in caplog.text


def test_no_password_appears_in_the_logs_even_on_a_wrong_password_rejection(caplog):
    user_store, rating_store = _make_stores()
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

    flush_directory()
    game_room_registry = GameRoomRegistry(send_fn, rating_store, RoomDirectory("test-shard"))
    router = ClientMessageRouter(game_room_registry, Matchmaker())
    disconnect_calls = []

    async def on_disconnect(participant):
        disconnect_calls.append(participant)
        await game_room_registry.remove_participant(participant)

    auth_gateway = AuthGateway(user_store)
    connection_handler = ConnectionHandler(rating_store, router)
    lifecycle = ConnectionLifecycle(auth_gateway, connection_handler, on_disconnect)
    return lifecycle, game_room_registry, disconnect_calls


def test_create_room_sequence_receives_role_then_snapshot_in_order():
    async def scenario():
        user_store, rating_store = _make_stores()
        lifecycle, _, _ = _make_real_lifecycle(user_store, rating_store)
        connection = FakeConnection([
            _login_message("alice"),
            json.dumps(message_to_payload(CreateRoomIntent())),
        ])

        await lifecycle.run(connection)

        sent_types = [json.loads(payload)["type"] for payload in connection.sent]
        assert sent_types == ["LoggedIn", "RoleAssigned", "GameSnapshot"]
        role_payload = json.loads(connection.sent[1])
        assert role_payload["role"] == "white"
        assert role_payload["room_id"]

    asyncio.run(scenario())


def test_join_with_an_unknown_room_id_receives_room_rejected_and_stays_in_lobby():
    async def scenario():
        user_store, rating_store = _make_stores()
        lifecycle, _, disconnect_calls = _make_real_lifecycle(user_store, rating_store)
        connection = FakeConnection([
            _login_message("alice"),
            json.dumps(message_to_payload(JoinRoomIntent(join_code="no-such-code"))),
        ])

        await lifecycle.run(connection)

        sent_types = [json.loads(payload)["type"] for payload in connection.sent]
        assert sent_types == ["LoggedIn", "RoomRejected"]
        assert disconnect_calls[0].room_id is None
        assert disconnect_calls[0].role is None

    asyncio.run(scenario())


def test_a_second_client_joining_an_existing_room_gets_black_and_the_rooms_real_snapshot():
    async def scenario():
        user_store, rating_store = _make_stores()
        lifecycle, game_room_registry, _ = _make_real_lifecycle(user_store, rating_store)
        creator_client = Participant(connection="creator-conn", username="creator")
        placement = game_room_registry.create_private_room(creator_client)

        second_connection = FakeConnection([
            _login_message("bob"),
            json.dumps(message_to_payload(JoinRoomIntent(join_code=placement.join_code))),
        ])

        await lifecycle.run(second_connection)

        sent_types = [json.loads(payload)["type"] for payload in second_connection.sent]
        assert sent_types == ["LoggedIn", "RoleAssigned", "GameSnapshot"]
        assert json.loads(second_connection.sent[1])["role"] == "black"

        expected_pieces = message_to_payload(placement.session.components.engine.snapshot())["pieces"]
        actual_pieces = json.loads(second_connection.sent[2])["pieces"]
        assert actual_pieces == expected_pieces

        await game_room_registry.remove_participant(creator_client)

    asyncio.run(scenario())
