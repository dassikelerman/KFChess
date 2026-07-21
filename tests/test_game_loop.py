import asyncio
import inspect

import server.game_loop as game_loop_module
from server.game_loop import run_game_loop


class FakeSession:
    def __init__(self):
        self.tick_calls = []

    def tick(self, dt_ms):
        self.tick_calls.append(dt_ms)


async def _run_briefly(session, publisher, tick_ms):
    task = asyncio.ensure_future(run_game_loop(session, publisher, tick_ms))
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def test_run_game_loop_passes_measured_elapsed_ms_to_session_tick():
    session = FakeSession()

    asyncio.run(_run_briefly(session, lambda: None, tick_ms=10))

    assert len(session.tick_calls) >= 1
    # Elapsed time is measured with a monotonic clock, not assumed to be
    # exactly tick_ms - just a small, non-negative integer number of ms.
    for dt_ms in session.tick_calls:
        assert isinstance(dt_ms, int)
        assert dt_ms >= 0


def test_run_game_loop_publishes_a_snapshot_after_every_tick():
    session = FakeSession()
    publish_calls = []

    asyncio.run(_run_briefly(session, lambda: publish_calls.append(None), tick_ms=10))

    assert len(publish_calls) == len(session.tick_calls)


def test_run_game_loop_calls_the_publisher_with_no_arguments():
    session = FakeSession()
    call_count = 0

    def publisher():
        nonlocal call_count
        call_count += 1

    asyncio.run(_run_briefly(session, publisher, tick_ms=10))

    assert call_count >= 1


def test_game_loop_module_has_no_websocket_specific_dependencies():
    # run_game_loop must stay transport-agnostic - websockets/JSON aren't
    # needed to sleep, measure elapsed time, tick the session, and call an
    # injected snapshot_publisher callback. Only the module's own imports
    # matter here, not its docstring's prose about what it avoids.
    imported_names = {
        name for name, value in vars(game_loop_module).items()
        if inspect.ismodule(value)
    }
    assert imported_names == {"asyncio", "time"}

    source = inspect.getsource(run_game_loop)
    assert "websockets" not in source
    assert "json" not in source
    assert "connection" not in source.lower()
