import subprocess
import sys
import time

from client.server_connection import EventReceived, ServerConnection, SnapshotReceived
from model.position import Position
from protocol.lobby_messages import LoggedIn, RoomCreated
from protocol.message_types import RoomAction
from server.ws_server import HOST, PORT

STARTUP_WAIT_S = 1
SNAPSHOT_TIMEOUT_S = 5
MOVE_LANDING_TIMEOUT_S = 8
WS_URL = f"ws://{HOST}:{PORT}"

SOURCE = Position(6, 0)
DESTINATION = Position(5, 0)


def _piece_at(snapshot, position):
    for piece in snapshot.pieces:
        if piece.row == position.row and piece.col == position.col:
            return piece
    return None


def _wait_for_event(connection, event_type, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = max(0.05, deadline - time.monotonic())
        item = connection.inbound.get(timeout=remaining)
        if isinstance(item, EventReceived) and isinstance(item.event, event_type):
            return item.event
    raise TimeoutError(f"no {event_type.__name__} received within {timeout}s")


def _wait_for_snapshot(connection, condition, timeout):
    deadline = time.monotonic() + timeout
    latest = None
    while time.monotonic() < deadline:
        remaining = max(0.05, deadline - time.monotonic())
        item = connection.inbound.get(timeout=remaining)
        if not isinstance(item, SnapshotReceived):
            continue
        latest = item.game_snapshot
        if condition(latest):
            return latest
    raise TimeoutError(f"condition not met within {timeout}s - last snapshot: {latest}")


def main():
    server_process = subprocess.Popen([sys.executable, "-m", "server.ws_server"])
    client_process = None
    try:
        time.sleep(STARTUP_WAIT_S)

        mover = ServerConnection(WS_URL)
        mover.start()
        mover.send_login("mover", "devpass")
        _wait_for_event(mover, LoggedIn, SNAPSHOT_TIMEOUT_S)
        mover.send_room_intent(RoomAction.CREATE)
        room_created = _wait_for_event(mover, RoomCreated, SNAPSHOT_TIMEOUT_S)
        print(f"OK: 'mover' created room {room_created.room_id!r} and is seated as white")

        client_process = subprocess.Popen([sys.executable, "-m", "client.run", WS_URL])
        print("A client window should open shortly.")
        print(f"To watch the same room, click Room and Join with id: {room_created.room_id}")

        before = _wait_for_snapshot(mover, condition=lambda s: True, timeout=SNAPSHOT_TIMEOUT_S)
        assert _piece_at(before, SOURCE) is not None, f"expected a piece at {SOURCE}"
        assert _piece_at(before, DESTINATION) is None, f"expected {DESTINATION} to start empty"
        print(f"OK: confirmed starting state - a piece sits at {SOURCE}, {DESTINATION} is empty.")

        mover.request_move(SOURCE, DESTINATION)
        _wait_for_snapshot(
            mover, condition=lambda s: _piece_at(s, DESTINATION) is not None,
            timeout=MOVE_LANDING_TIMEOUT_S,
        )
        print(f"PASS: MoveIntent({SOURCE} -> {DESTINATION}) actually moved the piece on the server.")

        print("Close the client window (or press Escape) to finish this check.")
        client_process.wait()
    finally:
        if client_process is not None and client_process.poll() is None:
            client_process.terminate()
        server_process.terminate()
        server_process.wait(timeout=5)


if __name__ == "__main__":
    main()
