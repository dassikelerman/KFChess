"""AuthService: verify a username/password and load the rating that goes with it.

The single dependency ClientSession needs for login, instead of reaching into two
separate datastores itself. Both blocking psycopg2 calls (UserStore.create_or_verify,
RatingStore.get_rating) run together off the event-loop thread via asyncio.to_thread, so
one slow login no longer stalls the single shared server loop that also ticks every
room (see server/ws_server.py). UserStore/RatingStore each guard their own connection
with a lock (see server/user_store.py, server/rating.py) since to_thread means their
connection can now be reached from a worker thread instead of always the event-loop
thread alone.
"""

import asyncio
from dataclasses import dataclass

from server.user_store import LoginResult


@dataclass(frozen=True)
class AuthenticatedIdentity:
    username: str
    rating: int


class AuthService:
    def __init__(self, user_store, rating_store):
        self._user_store = user_store
        self._rating_store = rating_store

    async def authenticate(self, username, password) -> AuthenticatedIdentity | None:
        return await asyncio.to_thread(self._authenticate_sync, username, password)

    def _authenticate_sync(self, username, password):
        if self._user_store.create_or_verify(username, password) is LoginResult.WRONG_PASSWORD:
            return None
        rating = self._rating_store.get_rating(username)
        return AuthenticatedIdentity(username=username, rating=rating)
