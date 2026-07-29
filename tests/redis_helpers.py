"""Shared Redis test helper.

Every test that needs a real RoomDirectory shares one Redis instance (docker compose
up), so each must call flush_directory() first instead of relying on process isolation -
same reasoning as tests/db_helpers.py's reset_users_table() for Postgres.
"""

import redis

from server.room_directory import DEFAULT_REDIS_URL


def flush_directory(redis_url=DEFAULT_REDIS_URL):
    redis.Redis.from_url(redis_url).flushdb()
