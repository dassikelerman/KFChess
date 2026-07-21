import subprocess
import sys
import time

from client.ws_client import WsClient
from model.position import Position
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


def _wait_for_snapshot(ws_client, condition, timeout):
    deadline = time.monotonic() + timeout
    latest = None
    while time.monotonic() < deadline:
        remaining = max(0.05, deadline - time.monotonic())
        item = ws_client.inbound.get(timeout=remaining)
        if item[0] != "snapshot":
            continue
        latest = item[1]
        if condition(latest):
            return latest
    raise TimeoutError(f"condition not met within {timeout}s - last snapshot: {latest}")


def main():
    server_process = subprocess.Popen([sys.executable, "-m", "server.ws_server"])
    client_process = None
    try:
        time.sleep(STARTUP_WAIT_S)

        client_process = subprocess.Popen([sys.executable, "-m", "client.run", WS_URL])
        print("A client window should open shortly - watch it for the same move below.")

        mover = WsClient(WS_URL)
        mover.start()
        mover.send_login("mover", "devpass")

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
