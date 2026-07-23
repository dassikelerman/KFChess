import hashlib
import secrets
import sqlite3

import constants

DEFAULT_DB_PATH = "server/kf_chess_users.db"
_PBKDF2_ITERATIONS = 200_000


def _hash_password(password, salt_hex):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), _PBKDF2_ITERATIONS,
    ).hex()


class UserStore:
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

    def create_or_verify(self, username, password):
        row = self._connection.execute(
            "SELECT password_hash, password_salt FROM users WHERE username = ?", (username,),
        ).fetchone()

        if row is None:
            salt = secrets.token_hex(16)
            self._connection.execute(
                "INSERT INTO users (username, password_hash, password_salt) VALUES (?, ?, ?)",
                (username, _hash_password(password, salt), salt),
            )
            self._connection.commit()
            return "created"

        stored_hash, salt = row
        if _hash_password(password, salt) == stored_hash:
            return "authenticated"
        return "wrong_password"
