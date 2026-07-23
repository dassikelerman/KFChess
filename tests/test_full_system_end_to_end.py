import asyncio
import json

import websockets

import server.ws_server as ws_server
from protocol.message_types import RoomAction
from protocol.game_messages import MoveIntent
from protocol.lobby_messages import Login, PlayIntent, RoomIntent
from protocol.registry import message_to_payload
from model.position import Position
from server.rating import RatingStore
from server.user_store import UserStore

RECV_TIMEOUT_S = 5
CLIENT_CLOSE_TIMEOUT_S = 2
MULTI_ROOM_PORT = 8796
FULL_SESSION_PORT = 8795

SOURCE = Position(6, 0)
DESTINATION = Position(5, 0)


async def _expect(connection, expected_type, timeout=RECV_TIMEOUT_S):
    raw = await asyncio.wait_for(connection.recv(), timeout=timeout)
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


async def _connect(uri):
    return await websockets.connect(uri, close_timeout=CLIENT_CLOSE_TIMEOUT_S)


def _piece_at(snapshot_payload, row, col):
    for piece in snapshot_payload["pieces"]:
        if piece["row"] == row and piece["col"] == col:
            return piece
    return None


async def _create_private_room(connection):
    await connection.send(json.dumps(message_to_payload(RoomIntent(action=RoomAction.CREATE))))
    room_created = await _expect(connection, "RoomCreated")
    await _expect(connection, "role")
    snapshot = await _expect(connection, "GameSnapshot")
    return room_created["room_id"], snapshot


async def _join_private_room(connection, room_id):
    await connection.send(json.dumps(message_to_payload(RoomIntent(action=RoomAction.JOIN, room_id=room_id))))
    await _expect(connection, "role")
    return await _expect(connection, "GameSnapshot")


async def _drain_recent_snapshots(connection, window=0.3):
    # An absolute deadline, not a "quiet for" gap - a room's game_loop ticks
    # continuously, so there's never a silent gap to wait out.
    deadline = asyncio.get_event_loop().time() + window
    latest = None
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            return latest
        try:
            raw = await asyncio.wait_for(connection.recv(), timeout=remaining)
        except asyncio.TimeoutError:
            return latest
        data = json.loads(raw)
        if data.get("type") == "GameSnapshot":
            latest = data


async def _send_move_and_wait_for_landing(sender, watcher, source, destination, timeout=8):
    await sender.send(json.dumps(message_to_payload(MoveIntent(source=source, destination=destination))))
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise TimeoutError(f"move {source}->{destination} never landed within {timeout}s")
        data = await _wait_for_type(watcher, "GameSnapshot", remaining)
        if _piece_at(data, destination.row, destination.col) is not None:
            return data


def test_concurrent_private_and_matched_rooms_do_not_leak_snapshots_or_events(tmp_path, monkeypatch):
    monkeypatch.setattr(ws_server, "PORT", MULTI_ROOM_PORT)
    db_path = str(tmp_path / "test_users.db")
    monkeypatch.setattr(ws_server, "UserStore", lambda: UserStore(db_path))
    monkeypatch.setattr(ws_server, "RatingStore", lambda: RatingStore(db_path))

    async def scenario():
        server_task = asyncio.create_task(ws_server.main())
        await asyncio.sleep(0.3)
        uri = f"ws://{ws_server.HOST}:{MULTI_ROOM_PORT}"

        connections = [await _connect(uri) for _ in range(6)]
        alice, bob, carol, dave, eve, frank = connections
        try:
            # Room A: private, alice (white) + bob (black).
            await _login(alice, "alice")
            room_a_id, _ = await _create_private_room(alice)
            await _login(bob, "bob")
            snapshot_bob = await _join_private_room(bob, room_a_id)

            # Room B: private, carol (white) + dave (black).
            await _login(carol, "carol")
            room_b_id, snapshot_carol = await _create_private_room(carol)
            await _login(dave, "dave")
            snapshot_dave = await _join_private_room(dave, room_b_id)

            # Room C: matched, eve + frank (both default to rating 1200, compatible).
            await _login(eve, "eve")
            await _login(frank, "frank")
            await eve.send(json.dumps(message_to_payload(PlayIntent())))
            await frank.send(json.dumps(message_to_payload(PlayIntent())))
            await _expect(eve, "role")
            snapshot_eve = await _expect(eve, "GameSnapshot")
            await _expect(frank, "role")
            snapshot_frank = await _expect(frank, "GameSnapshot")

            pristine_pieces = snapshot_carol["pieces"]
            assert snapshot_bob["pieces"] == pristine_pieces
            assert snapshot_dave["pieces"] == pristine_pieces
            assert snapshot_eve["pieces"] == pristine_pieces
            assert snapshot_frank["pieces"] == pristine_pieces

            # A move only in room A must never surface in room B or room C.
            await _send_move_and_wait_for_landing(alice, bob, SOURCE, DESTINATION)

            for connection in (carol, dave, eve, frank):
                latest = await _drain_recent_snapshots(connection)
                assert latest is not None
                assert _piece_at(latest, DESTINATION.row, DESTINATION.col) is None
                assert _piece_at(latest, SOURCE.row, SOURCE.col) is not None
        finally:
            for connection in connections:
                await connection.close()
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass

    asyncio.run(scenario())


def test_a_full_realistic_session_ends_in_disconnect_resign_and_rating_updates(tmp_path, monkeypatch):
    monkeypatch.setattr(ws_server, "PORT", FULL_SESSION_PORT)
    db_path = str(tmp_path / "test_users.db")
    monkeypatch.setattr(ws_server, "UserStore", lambda: UserStore(db_path))
    monkeypatch.setattr(ws_server, "RatingStore", lambda: RatingStore(db_path))
    monkeypatch.setattr(ws_server, "DISCONNECT_COUNTDOWN_SECONDS", 1)

    async def scenario():
        server_task = asyncio.create_task(ws_server.main())
        await asyncio.sleep(0.3)
        uri = f"ws://{ws_server.HOST}:{FULL_SESSION_PORT}"

        alice = await _connect(uri)
        bob = await _connect(uri)
        try:
            logged_in_alice = await _login(alice, "alice")
            assert logged_in_alice["rating"] == 1200
            logged_in_bob = await _login(bob, "bob")
            assert logged_in_bob["rating"] == 1200

            room_id, _ = await _create_private_room(alice)
            await _join_private_room(bob, room_id)

            # Several real moves, alternating sides - a realistic mid-game slice.
            await _send_move_and_wait_for_landing(alice, bob, Position(6, 0), Position(5, 0))
            await _send_move_and_wait_for_landing(bob, alice, Position(1, 0), Position(2, 0))
            await _send_move_and_wait_for_landing(alice, bob, Position(6, 1), Position(5, 1))

            await alice.close()  # alice (white) disconnects mid-game

            disconnected = await _wait_for_type(bob, "PlayerDisconnectedEvent", timeout=5)
            assert disconnected["color"] == "w"

            game_over = await _wait_for_type(bob, "GameOverEvent", timeout=5)
            assert game_over["winner_color"] == "b"
        finally:
            await bob.close()
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass

        rating_store = RatingStore(db_path)
        # Equal starting ratings (1200), black win: white loses, black gains.
        assert rating_store.get_rating("alice") == 1184
        assert rating_store.get_rating("bob") == 1216

    asyncio.run(scenario())
