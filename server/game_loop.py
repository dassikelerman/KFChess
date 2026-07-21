"""The server's tick loop, extracted out of server/ws_server.py so it has
no knowledge of WebSockets, JSON, or connections - just Session.tick()
and a snapshot_publisher callback injected by the caller, the same
"no knowledge of transport" separation server/network_publisher.py
already has via its own injected broadcast_fn/unicast_fn."""

import asyncio
import time


async def run_game_loop(session, snapshot_publisher, tick_ms):
    interval = tick_ms / 1000
    last_tick = time.perf_counter()
    while True:
        await asyncio.sleep(interval)
        now = time.perf_counter()
        dt_ms = round((now - last_tick) * 1000)
        last_tick = now

        session.tick(dt_ms)
        snapshot_publisher()
