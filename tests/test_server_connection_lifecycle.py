"""Regression coverage for ServerConnection's background thread actually terminating.

_receive() and _send() run side by side inside one background thread. A clean
(code 1000) server-side close ends _receive()'s loop with no exception at all - these
tests prove that no longer leaves _send() (and its underlying executor thread) blocked
on the outbound queue forever, which would otherwise leave the whole background thread,
and eventually the process, unable to exit.
"""

import asyncio
import threading

import websockets

from client.server_connection import ServerConnection

THREAD_JOIN_TIMEOUT_S = 5
SERVER_READY_TIMEOUT_S = 5
TEST_PORT = 8802


def _serve_one_connection_then_close_cleanly(port, ready_event, close_after_s=0.1):
    async def handler(websocket):
        await asyncio.sleep(close_after_s)
        await websocket.close(code=1000, reason="server done")

    async def serve():
        async with websockets.serve(handler, "localhost", port):
            ready_event.set()
            await asyncio.sleep(THREAD_JOIN_TIMEOUT_S + SERVER_READY_TIMEOUT_S)

    thread = threading.Thread(target=lambda: asyncio.run(serve()), daemon=True)
    thread.start()
    ready_event.wait(timeout=SERVER_READY_TIMEOUT_S)
    return thread


def test_a_clean_server_side_close_terminates_the_background_thread():
    # Regression test for the asyncio.gather() deadlock: gather() only returns early
    # when one side *raises*, but a clean server close ends _receive() with no
    # exception, so gather() would wait forever for _send() - which has nothing queued
    # to wake it. If this hangs, the fix in _run_receive_and_send regressed.
    ready_event = threading.Event()
    _serve_one_connection_then_close_cleanly(TEST_PORT, ready_event)

    connection = ServerConnection(f"ws://localhost:{TEST_PORT}")
    connection.start()

    connection._thread.join(timeout=THREAD_JOIN_TIMEOUT_S)

    assert not connection._thread.is_alive(), (
        "ServerConnection's background thread is still alive after a clean "
        "server-side close - _send() is deadlocked waiting on the outbound queue"
    )


def test_calling_close_still_terminates_the_background_thread():
    # The original (already-fixed) scenario: the app itself decides to close. Kept
    # here alongside the server-initiated case so both ways a connection can end are
    # covered by one thread-level regression test file.
    ready_event = threading.Event()
    _serve_one_connection_then_close_cleanly(TEST_PORT + 1, ready_event, close_after_s=10)

    connection = ServerConnection(f"ws://localhost:{TEST_PORT + 1}")
    connection.start()
    connection.close()

    connection._thread.join(timeout=THREAD_JOIN_TIMEOUT_S)

    assert not connection._thread.is_alive(), (
        "ServerConnection's background thread is still alive after close() - "
        "the outbound close sentinel never unblocked _send()"
    )
