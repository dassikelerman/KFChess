"""Shared Postgres test helper.

UserStore/RatingStore used to get test isolation for free - each test pointed at its own
sqlite file (or ":memory:"). Now that both talk to one real, shared Postgres instance
(docker compose up), every test that needs a real UserStore/RatingStore must call
reset_users_table() first instead, so it always starts from an empty table.
"""

import psycopg2

from server.user_store import DEFAULT_DATABASE_URL


def reset_users_table(database_url=DEFAULT_DATABASE_URL):
    connection = psycopg2.connect(database_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS users")
        connection.commit()
    finally:
        connection.close()
