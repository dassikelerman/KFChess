import hashlib
import os
import secrets
from enum import StrEnum

import psycopg2

import constants

# Matches docker-compose.yml's postgres service by default; override with
# KFCHESS_DATABASE_URL to point at a different instance.
DEFAULT_DATABASE_URL = os.environ.get(
    "KFCHESS_DATABASE_URL", "postgresql://kfchess:kfchess@localhost:5432/kfchess",
)
_PBKDF2_ITERATIONS = 200_000


class LoginResult(StrEnum):
    CREATED = "created"
    AUTHENTICATED = "authenticated"
    WRONG_PASSWORD = "wrong_password"


def _hash_password(password, salt_hex):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), _PBKDF2_ITERATIONS,
    ).hex()


class UserStore:
    def __init__(self, database_url=DEFAULT_DATABASE_URL):
        # autocommit: every statement below is already a single logical unit, and this
        # avoids a real trap otherwise - psycopg2 opens an implicit transaction on the
        # first statement of a connection, even a plain SELECT, and it stays open (idle,
        # holding a lock) until an explicit commit/rollback. A read-only path that forgot
        # to commit could sit on a connection indefinitely and block a later DROP TABLE.
        self._connection = psycopg2.connect(database_url)
        self._connection.autocommit = True
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

    def create_or_verify(self, username, password):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT password_hash, password_salt FROM users WHERE username = %s", (username,),
            )
            row = cursor.fetchone()

            if row is None:
                salt = secrets.token_hex(16)
                cursor.execute(
                    "INSERT INTO users (username, password_hash, password_salt) VALUES (%s, %s, %s)",
                    (username, _hash_password(password, salt), salt),
                )
                return LoginResult.CREATED

        stored_hash, salt = row
        if _hash_password(password, salt) == stored_hash:
            return LoginResult.AUTHENTICATED
        return LoginResult.WRONG_PASSWORD
