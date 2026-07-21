import asyncio
import time


async def run_game_loop(session, broadcast_snapshot, tick_ms):
    interval = tick_ms / 1000
    last_tick = time.perf_counter()
    while True:
        await asyncio.sleep(interval)
        now = time.perf_counter()
        dt_ms = round((now - last_tick) * 1000)
        last_tick = now

        session.tick(dt_ms)
        broadcast_snapshot()
