import asyncio
import time

from server.auth_service import AuthenticatedIdentity, AuthService
from server.user_store import LoginResult


class FakeUserStore:
    def __init__(self, result=LoginResult.AUTHENTICATED, delay_s=0):
        self._result = result
        self._delay_s = delay_s
        self.calls = []

    def create_or_verify(self, username, password):
        self.calls.append((username, password))
        if self._delay_s:
            time.sleep(self._delay_s)
        return self._result


class FakeRatingStore:
    def __init__(self, rating=1200):
        self._rating = rating
        self.calls = []

    def get_rating(self, username):
        self.calls.append(username)
        return self._rating


def test_a_correct_login_returns_the_identity_with_its_rating():
    auth_service = AuthService(FakeUserStore(), FakeRatingStore(rating=1350))

    identity = asyncio.run(auth_service.authenticate("alice", "hunter2"))

    assert identity == AuthenticatedIdentity(username="alice", rating=1350)


def test_a_wrong_password_returns_none_and_never_looks_up_a_rating():
    rating_store = FakeRatingStore()
    auth_service = AuthService(FakeUserStore(result=LoginResult.WRONG_PASSWORD), rating_store)

    identity = asyncio.run(auth_service.authenticate("alice", "wrong"))

    assert identity is None
    assert rating_store.calls == []


def test_a_slow_authenticate_call_does_not_block_other_coroutines_on_the_event_loop():
    # Regression test for the actual bug: UserStore/RatingStore are plain synchronous
    # psycopg2 - without asyncio.to_thread inside AuthService, an `await` on a slow
    # authenticate() would stall the *entire* event loop, including every other room's
    # tick (see server/ws_server.py's single shared server loop). A concurrent coroutine
    # that just increments a counter every 10ms should keep making progress while a
    # slow login is "in flight".
    auth_service = AuthService(FakeUserStore(delay_s=0.3), FakeRatingStore())
    ticks = []

    async def tick_loop():
        for _ in range(20):
            await asyncio.sleep(0.01)
            ticks.append(1)

    async def scenario():
        await asyncio.gather(auth_service.authenticate("alice", "hunter2"), tick_loop())

    asyncio.run(scenario())

    # If authenticate() were blocking the loop for its whole 0.3s, far fewer than 20
    # ticks would have had a chance to run in that window.
    assert len(ticks) >= 15
