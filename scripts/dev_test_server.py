import asyncio
import json

import websockets

from protocol.lobby_messages import Login, RoomIntent
from protocol.message_types import RoomAction
from protocol.registry import message_to_payload
from server import ws_server

RECV_TIMEOUT_S = 5
BROADCASTS_TO_OBSERVE = 3


async def _expect(connection, expected_type):
    raw = await asyncio.wait_for(connection.recv(), timeout=RECV_TIMEOUT_S)
    data = json.loads(raw)
    assert data["type"] == expected_type, f"expected type={expected_type!r}, got {data}"
    return data


async def _login(connection, username):
    await connection.send(json.dumps(message_to_payload(Login(username=username, password="devpass"))))
    await _expect(connection, "LoggedIn")


async def _create_room(connection, username):
    await _login(connection, username)
    await connection.send(json.dumps(message_to_payload(RoomIntent(action=RoomAction.CREATE))))
    room_created = await _expect(connection, "RoomCreated")
    role_message = await _expect(connection, "role")
    assert role_message["role"] == "white", role_message
    await _expect(connection, "GameSnapshot")
    print(f"OK: {username!r} created room {room_created['room_id']!r} and is seated as white")
    return room_created["room_id"]


async def _join_room(connection, username, room_id, expected_role):
    await _login(connection, username)
    await connection.send(json.dumps(message_to_payload(RoomIntent(action=RoomAction.JOIN, room_id=room_id))))
    role_message = await _expect(connection, "role")
    assert role_message["role"] == expected_role, role_message
    await _expect(connection, "GameSnapshot")
    print(f"OK: {username!r} joined room {room_id!r} and is seated as {expected_role!r}")


async def main():
    server_task = asyncio.create_task(ws_server.main())
    await asyncio.sleep(0.5)

    uri = f"ws://{ws_server.HOST}:{ws_server.PORT}"
    client_a = None
    client_b = None
    try:
        client_a = await websockets.connect(uri)
        room_id = await _create_room(client_a, "alice")

        client_b = await websockets.connect(uri)
        await _join_room(client_b, "bob", room_id, "black")

        for i in range(BROADCASTS_TO_OBSERVE):
            await _expect(client_a, "GameSnapshot")
            await _expect(client_b, "GameSnapshot")
            print(f"OK: both connections received tick broadcast #{i + 1}")

        print("PASS: room creation/join and periodic snapshot broadcasts both work.")
    finally:
        if client_a is not None:
            await client_a.close()
        if client_b is not None:
            await client_b.close()
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
