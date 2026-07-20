"""Manual check for client/run.py against the real server - step 4 of
the client/server migration (docs/kf-chess-architecture-plan.md).
Starts the Step 3 server as a subprocess, then runs the real client
loop (client.run.run) in this process so its cv2 window is visible.

This is NOT an automated test and asserts nothing: a human needs to
actually look at the window and confirm the board renders and stays
in sync as the server ticks (piece positions, the clock-driven rest
overlay, etc.) - there is no attempt here to assert on pixel output,
that would be testing OpenCV/asset rendering, not this step's wiring.

Press Escape or close the window to end the check; the server
subprocess is torn down afterward either way.

Run directly: python -m scripts.dev_test_client
"""

import subprocess
import sys
import time

from client.run import run
from server.ws_server import HOST, PORT

STARTUP_WAIT_S = 1
WS_URL = f"ws://{HOST}:{PORT}"


def main():
    server_process = subprocess.Popen([sys.executable, "-m", "server.ws_server"])
    try:
        time.sleep(STARTUP_WAIT_S)  # give the server a moment to start listening
        print(f"Connecting to {WS_URL} - a window should open shortly.")
        print("Watch it update live as the server ticks, then press Escape")
        print("or close the window to finish this check.")
        run(WS_URL)
    finally:
        server_process.terminate()
        server_process.wait(timeout=5)


if __name__ == "__main__":
    main()
