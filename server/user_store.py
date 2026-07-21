import hashlib
import secrets
import sqlite3

DEFAULT_DB_PATH = "server/kf_chess_users.db"
DEFAULT_RATING = 1200
K_FACTOR = 32
_PBKDF2_ITERATIONS = 200_000


def _hash_password(password, salt_hex):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), _PBKDF2_ITERATIONS,
    ).hex()


def _expected_score(rating, opponent_rating):
    return 1 / (1 + 10 ** ((opponent_rating - rating) / 400))


def _actual_scores(winner_color):
    if winner_color == "white":
        return 1, 0
    if winner_color == "black":
        return 0, 1
    return 0.5, 0.5


class UserStore:
    def __init__(self, db_path=DEFAULT_DB_PATH):
        self._connection = sqlite3.connect(db_path)
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                rating INTEGER DEFAULT 1200
            )
            """
        )
        self._connection.commit()

    def create_or_verify(self, username, password):
        row = self._connection.execute(
            "SELECT password_hash, password_salt FROM users WHERE username = ?", (username,),
        ).fetchone()

        if row is None:
            salt = secrets.token_hex(16)
            self._connection.execute(
                "INSERT INTO users (username, password_hash, password_salt, rating) VALUES (?, ?, ?, ?)",
                (username, _hash_password(password, salt), salt, DEFAULT_RATING),
            )
            self._connection.commit()
            return "created"

        stored_hash, salt = row
        if _hash_password(password, salt) == stored_hash:
            return "authenticated"
        return "wrong_password"

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

        new_white = round(white_rating + K_FACTOR * (white_score - white_expected))
        new_black = round(black_rating + K_FACTOR * (black_score - black_expected))

        self._connection.execute("UPDATE users SET rating = ? WHERE username = ?", (new_white, white_username))
        self._connection.execute("UPDATE users SET rating = ? WHERE username = ?", (new_black, black_username))
        self._connection.commit()
        return new_white, new_black
