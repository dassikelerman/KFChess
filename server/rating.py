import sqlite3

import constants
from server.user_store import DEFAULT_DB_PATH


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
    def __init__(self, db_path=DEFAULT_DB_PATH):
        self._connection = sqlite3.connect(db_path)
        self._connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                rating INTEGER DEFAULT {constants.STARTING_RATING}
            )
            """
        )
        self._connection.commit()

    def get_rating(self, username):
        row = self._connection.execute(
            "SELECT rating FROM users WHERE username = ?", (username,),
        ).fetchone()
        return row[0]

    def update_ratings(self, white_username, black_username, winner_color):
        white_rating = self.get_rating(white_username)
        black_rating = self.get_rating(black_username)

        white_score, black_score = _actual_scores(winner_color)
        white_expected = _expected_score(white_rating, black_rating)
        black_expected = _expected_score(black_rating, white_rating)

        new_white = round(white_rating + constants.RATING_K_FACTOR * (white_score - white_expected))
        new_black = round(black_rating + constants.RATING_K_FACTOR * (black_score - black_expected))

        self._connection.execute("UPDATE users SET rating = ? WHERE username = ?", (new_white, white_username))
        self._connection.execute("UPDATE users SET rating = ? WHERE username = ?", (new_black, black_username))
        self._connection.commit()
        return new_white, new_black
