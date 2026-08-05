import threading

import psycopg2

import constants
from server.user_store import DEFAULT_DATABASE_URL


def _expected_score(rating, opponent_rating):
    return 1 / (1 + 10 ** ((opponent_rating - rating) / 400))


def _actual_scores(winner_color):
    # Plain "white"/"black" strings on purpose - rating math has no reason to
    # depend on model.piece.PieceColor or server.session's role/color split.
    if winner_color == "white":
        return 1, 0
    if winner_color == "black":
        return 0, 1
    return 0.5, 0.5


class RatingStore:
    def __init__(self, database_url=DEFAULT_DATABASE_URL):
        # autocommit - see the matching comment in UserStore.__init__: without it, a
        # read-only get_rating() would leave an idle-in-transaction connection that could
        # later block a DROP TABLE from some other, unrelated connection.
        self._connection = psycopg2.connect(database_url)
        self._connection.autocommit = True
        # AuthService (server/auth_service.py) runs get_rating off the event-loop thread
        # via asyncio.to_thread, so this connection can now be touched from a worker
        # thread concurrently with update_ratings running on the main thread inside a
        # room's tick - the lock keeps every method here to one caller at a time.
        self._lock = threading.Lock()
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
                    rating INTEGER DEFAULT {constants.STARTING_RATING}
                )
                """
            )

    def get_rating(self, username):
        with self._lock, self._connection.cursor() as cursor:
            cursor.execute("SELECT rating FROM users WHERE username = %s", (username,))
            row = cursor.fetchone()
        return row[0]

    def update_ratings(self, white_username, black_username, winner_color):
        with self._lock:
            return self._update_ratings_locked(white_username, black_username, winner_color)

    def _update_ratings_locked(self, white_username, black_username, winner_color):
        white_rating = self._get_rating_locked(white_username)
        black_rating = self._get_rating_locked(black_username)

        white_score, black_score = _actual_scores(winner_color)
        white_expected = _expected_score(white_rating, black_rating)
        black_expected = _expected_score(black_rating, white_rating)

        new_white = round(white_rating + constants.RATING_K_FACTOR * (white_score - white_expected))
        new_black = round(black_rating + constants.RATING_K_FACTOR * (black_score - black_expected))

        # Both rows must land together or not at all - the one place here where two
        # statements need real transactional atomicity, not autocommit's one-statement-
        # at-a-time default. Restoring autocommit in `finally` keeps every other method
        # (get_rating, create_or_verify) safe from ever sitting idle-in-transaction.
        self._connection.autocommit = False
        try:
            with self._connection.cursor() as cursor:
                cursor.execute("UPDATE users SET rating = %s WHERE username = %s", (new_white, white_username))
                cursor.execute("UPDATE users SET rating = %s WHERE username = %s", (new_black, black_username))
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        finally:
            self._connection.autocommit = True

        return new_white, new_black

    def _get_rating_locked(self, username):
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT rating FROM users WHERE username = %s", (username,))
            return cursor.fetchone()[0]
