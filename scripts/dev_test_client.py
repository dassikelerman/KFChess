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
        time.sleep(STARTUP_WAIT_S)
        print(f"Connecting to {WS_URL} - a window should open shortly.")
        print("Watch it update live as the server ticks, then press Escape")
        print("or close the window to finish this check.")
        run(WS_URL)
    finally:
        server_process.terminate()
        server_process.wait(timeout=5)


if __name__ == "__main__":
    main()
