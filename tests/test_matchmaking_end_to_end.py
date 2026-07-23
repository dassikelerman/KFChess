import asyncio
import json

import websockets

import server.ws_server as ws_server
from protocol.lobby_messages import Login, PlayIntent
from protocol.registry import message_to_payload
from server.rating import RatingStore
from server.user_store import UserStore

RECV_TIMEOUT_S = 5
CLIENT_CLOSE_TIMEOUT_S = 2
TEST_PORT = 8798


async def _expect(connection, expected_type, timeout=RECV_TIMEOUT_S):
    raw = await asyncio.wait_for(connection.recv(), timeout=timeout)
    data = json.loads(raw)
    assert data["type"] == expected_type, f"expected type={expected_type!r}, got {data}"
    return data


async def _login(connection, username):
    await connection.send(json.dumps(message_to_payload(Login(username=username, password="devpass"))))
    return await _expect(connection, "LoggedIn")


async def _connect(uri):
    return await websockets.connect(uri, close_timeout=CLIENT_CLOSE_TIMEOUT_S)


def test_two_compatible_players_are_matched_and_a_third_incompatible_player_expires(tmp_path, monkeypatch):
    monkeypatch.setattr(ws_server, "PORT", TEST_PORT)
    db_path = str(tmp_path / "test_users.db")
    shared_user_store = UserStore(db_path)
    shared_rating_store = RatingStore(db_path)
    monkeypatch.setattr(ws_server, "UserStore", lambda: shared_user_store)
    monkeypatch.setattr(ws_server, "RatingStore", lambda: shared_rating_store)
    monkeypatch.setattr(ws_server, "MATCH_EXPIRY_S", 1)
    monkeypatch.setattr(ws_server, "EXPIRY_POLL_S", 0.2)

    # alice and bob keep the default 1200 rating (compatible). carol is bumped
    # far outside the +/-100 tolerance so she stays queued until she expires.
    shared_user_store.create_or_verify("carol", "devpass")
    shared_rating_store._connection.execute("UPDATE users SET rating = ? WHERE username = ?", (1500, "carol"))
    shared_rating_store._connection.commit()

    async def scenario():
        server_task = asyncio.create_task(ws_server.main())
        await asyncio.sleep(0.3)

        uri = f"ws://{ws_server.HOST}:{TEST_PORT}"
        client_a = await _connect(uri)
        client_b = await _connect(uri)
        client_c = await _connect(uri)
        try:
            await _login(client_a, "alice")
            await _login(client_b, "bob")
            await _login(client_c, "carol")

            await client_a.send(json.dumps(message_to_payload(PlayIntent())))
            await client_b.send(json.dumps(message_to_payload(PlayIntent())))

            role_a = await _expect(client_a, "role")
            snapshot_a = await _expect(client_a, "GameSnapshot")
            role_b = await _expect(client_b, "role")
            snapshot_b = await _expect(client_b, "GameSnapshot")

            assert {role_a["role"], role_b["role"]} == {"white", "black"}
            assert snapshot_a["pieces"] == snapshot_b["pieces"]

            await client_c.send(json.dumps(message_to_payload(PlayIntent())))
            match_not_found = await _expect(client_c, "MatchNotFound", timeout=5)
            assert match_not_found["reason"]
        finally:
            await client_a.close()
            await client_b.close()
            await client_c.close()
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass

    asyncio.run(scenario())
