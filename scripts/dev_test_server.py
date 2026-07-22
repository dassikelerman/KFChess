import asyncio
import json

import websockets

from protocol.serialization import Login, to_dict
from server import ws_server

RECV_TIMEOUT_S = 5
BROADCASTS_TO_OBSERVE = 3


async def _expect(connection, expected_type):
    raw = await asyncio.wait_for(connection.recv(), timeout=RECV_TIMEOUT_S)
    data = json.loads(raw)
    assert data["type"] == expected_type, f"expected type={expected_type!r}, got {data}"
    return data


async def _connect_and_check_seat(uri, username, expected_role):
    connection = await websockets.connect(uri)
    await connection.send(json.dumps(to_dict(Login(username=username, password="devpass"))))
    role_message = await _expect(connection, "role")
    assert role_message["role"] == expected_role, role_message
    await _expect(connection, "GameSnapshot")
    print(f"OK: {username!r} seated as {expected_role!r} and received its initial snapshot")
    return connection


async def main():
    server_task = asyncio.create_task(ws_server.main())
    await asyncio.sleep(0.5)

    uri = f"ws://{ws_server.HOST}:{ws_server.PORT}"
    client_a = None
    client_b = None
    try:
        client_a = await _connect_and_check_seat(uri, "alice", "white")
        client_b = await _connect_and_check_seat(uri, "bob", "black")

        for i in range(BROADCASTS_TO_OBSERVE):
            await _expect(client_a, "GameSnapshot")
            await _expect(client_b, "GameSnapshot")
            print(f"OK: both connections received tick broadcast #{i + 1}")

        print("PASS: role assignment and periodic snapshot broadcasts both work.")
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
