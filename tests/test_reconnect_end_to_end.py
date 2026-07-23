import asyncio
import json

import pytest
import websockets

import server.ws_server as ws_server
from protocol.message_types import RoomAction
from protocol.lobby_messages import Login, RoomIntent
from protocol.registry import message_to_payload
from server.rating import RatingStore
from server.user_store import UserStore

RECV_TIMEOUT_S = 5
CLIENT_CLOSE_TIMEOUT_S = 2
TEST_PORT = 8798


async def _expect(connection, expected_type):
    raw = await asyncio.wait_for(connection.recv(), timeout=RECV_TIMEOUT_S)
    data = json.loads(raw)
    assert data["type"] == expected_type, f"expected type={expected_type!r}, got {data}"
    return data


async def _wait_for_type(connection, expected_type, timeout):
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise TimeoutError(f"never received a {expected_type!r} message within {timeout}s")
        raw = await asyncio.wait_for(connection.recv(), timeout=remaining)
        data = json.loads(raw)
        if data.get("type") == expected_type:
            return data


async def _login(connection, username):
    await connection.send(json.dumps(message_to_payload(Login(username=username, password="devpass"))))
    return await _expect(connection, "LoggedIn")


def test_reconnecting_with_the_same_username_within_the_grace_window_rejoins_the_room(tmp_path, monkeypatch):
    monkeypatch.setattr(ws_server, "PORT", TEST_PORT)
    db_path = str(tmp_path / "test_users.db")
    monkeypatch.setattr(ws_server, "UserStore", lambda: UserStore(db_path))
    monkeypatch.setattr(ws_server, "RatingStore", lambda: RatingStore(db_path))
    monkeypatch.setattr(ws_server, "DISCONNECT_COUNTDOWN_SECONDS", 20)

    async def scenario():
        server_task = asyncio.create_task(ws_server.main())
        await asyncio.sleep(0.3)

        uri = f"ws://{ws_server.HOST}:{TEST_PORT}"
        client_a = await websockets.connect(uri, close_timeout=CLIENT_CLOSE_TIMEOUT_S)
        client_b = await websockets.connect(uri, close_timeout=CLIENT_CLOSE_TIMEOUT_S)
        client_a2 = None
        try:
            await _login(client_a, "alice")
            await _login(client_b, "bob")

            await client_a.send(json.dumps(message_to_payload(RoomIntent(action=RoomAction.CREATE))))
            room_created = await _expect(client_a, "RoomCreated")
            await _expect(client_a, "role")
            await _expect(client_a, "GameSnapshot")

            room_id = room_created["room_id"]
            await client_b.send(json.dumps(message_to_payload(RoomIntent(action=RoomAction.JOIN, room_id=room_id))))
            await _expect(client_b, "role")
            await _expect(client_b, "GameSnapshot")

            await client_a.close()  # alice (white) drops mid-game

            disconnected = await _wait_for_type(client_b, "PlayerDisconnectedEvent", timeout=5)
            assert disconnected["color"] == "w"

            # alice logs back in on a brand new connection, still inside the 20s grace window -
            # the server should push her straight back into her old seat, no RoomIntent/PlayIntent needed.
            client_a2 = await websockets.connect(uri, close_timeout=CLIENT_CLOSE_TIMEOUT_S)
            await _login(client_a2, "alice")
            role = await _expect(client_a2, "role")
            assert role["role"] == "white"
            await _expect(client_a2, "GameSnapshot")

            reconnected = await _wait_for_type(client_b, "PlayerReconnectedEvent", timeout=5)
            assert reconnected["color"] == "w"

            # the game must still be alive - no resign should ever arrive now.
            with pytest.raises(TimeoutError):
                await _wait_for_type(client_b, "GameOverEvent", timeout=3)
        finally:
            await client_b.close()
            if client_a2 is not None:
                await client_a2.close()
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass

    asyncio.run(scenario())
