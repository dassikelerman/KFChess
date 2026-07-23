import asyncio
import json

import websockets

import server.ws_server as ws_server
from protocol.message_types import RoomAction
from protocol.game_messages import MoveIntent
from protocol.lobby_messages import Login, RoomIntent
from protocol.registry import message_to_payload
from model.position import Position
from server.rating import RatingStore
from server.user_store import UserStore

RECV_TIMEOUT_S = 5
MOVE_LANDING_TIMEOUT_S = 8
CLIENT_CLOSE_TIMEOUT_S = 2
TEST_PORT = 8799

SOURCE = Position(6, 0)
DESTINATION = Position(5, 0)


async def _expect(connection, expected_type):
    raw = await asyncio.wait_for(connection.recv(), timeout=RECV_TIMEOUT_S)
    data = json.loads(raw)
    assert data["type"] == expected_type, f"expected type={expected_type!r}, got {data}"
    return data


async def _login(connection, username):
    await connection.send(json.dumps(message_to_payload(Login(username=username, password="devpass"))))
    return await _expect(connection, "LoggedIn")


async def _connect(uri):
    return await websockets.connect(uri, close_timeout=CLIENT_CLOSE_TIMEOUT_S)


async def _wait_for_condition(connection, condition, timeout):
    deadline = asyncio.get_event_loop().time() + timeout
    latest = None
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise TimeoutError(f"condition not met within {timeout}s - last snapshot: {latest}")
        raw = await asyncio.wait_for(connection.recv(), timeout=remaining)
        data = json.loads(raw)
        if data.get("type") != "GameSnapshot":
            continue
        latest = data
        if condition(latest):
            return latest


def _piece_at(snapshot_payload, row, col):
    for piece in snapshot_payload["pieces"]:
        if piece["row"] == row and piece["col"] == col:
            return piece
    return None


def test_login_create_room_join_room_and_a_move_is_visible_to_both(tmp_path, monkeypatch):
    monkeypatch.setattr(ws_server, "PORT", TEST_PORT)
    db_path = str(tmp_path / "test_users.db")
    monkeypatch.setattr(ws_server, "UserStore", lambda: UserStore(db_path))
    monkeypatch.setattr(ws_server, "RatingStore", lambda: RatingStore(db_path))

    async def scenario():
        server_task = asyncio.create_task(ws_server.main())
        await asyncio.sleep(0.3)

        uri = f"ws://{ws_server.HOST}:{TEST_PORT}"
        client_a = await _connect(uri)
        client_b = None
        try:
            logged_in_a = await _login(client_a, "alice")
            assert logged_in_a["username"] == "alice"
            assert logged_in_a["rating"] == 1200

            await client_a.send(json.dumps(message_to_payload(RoomIntent(action=RoomAction.CREATE))))
            room_created = await _expect(client_a, "RoomCreated")
            room_id = room_created["room_id"]
            role_a = await _expect(client_a, "role")
            assert role_a["role"] == "white"
            snapshot_a = await _expect(client_a, "GameSnapshot")

            client_b = await _connect(uri)
            await _login(client_b, "bob")
            await client_b.send(json.dumps(message_to_payload(RoomIntent(action=RoomAction.JOIN, room_id=room_id))))
            role_b = await _expect(client_b, "role")
            assert role_b["role"] == "black"
            snapshot_b = await _expect(client_b, "GameSnapshot")

            assert snapshot_a["pieces"] == snapshot_b["pieces"]
            assert _piece_at(snapshot_a, SOURCE.row, SOURCE.col) is not None
            assert _piece_at(snapshot_a, DESTINATION.row, DESTINATION.col) is None

            move = MoveIntent(source=SOURCE, destination=DESTINATION)
            await client_a.send(json.dumps(message_to_payload(move)))

            landed = await _wait_for_condition(
                client_b, lambda data: _piece_at(data, DESTINATION.row, DESTINATION.col) is not None,
                MOVE_LANDING_TIMEOUT_S,
            )
            assert _piece_at(landed, SOURCE.row, SOURCE.col) is None
        finally:
            await client_a.close()
            if client_b is not None:
                await client_b.close()
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass

    asyncio.run(scenario())
