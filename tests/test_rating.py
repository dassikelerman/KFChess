import pytest

from tests.db_helpers import reset_users_table

from server.rating import RatingStore
from server.user_store import UserStore


def _make_stores():
    reset_users_table()
    return UserStore(), RatingStore()


class _FailOnSecondUpdateCursor:
    """Wraps a real cursor so the second UPDATE in a batch raises - proves
    update_ratings rolls back the first UPDATE too, instead of leaving one
    color's rating changed and the other not."""

    def __init__(self, real_cursor, counters):
        self._real = real_cursor
        self._counters = counters

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return self._real.__exit__(*exc_info)

    def execute(self, sql, params=None):
        if sql.strip().upper().startswith("UPDATE"):
            self._counters["update_calls"] += 1
            if self._counters["update_calls"] == 2:
                raise RuntimeError("simulated failure on the second UPDATE")
        return self._real.execute(sql, params)

    def fetchone(self):
        return self._real.fetchone()


class _ConnectionThatFailsSecondUpdate:
    """Delegates everything to a real connection, except cursor() returns a
    cursor that fails on the second UPDATE - see _FailOnSecondUpdateCursor."""

    def __init__(self, real_connection):
        self.real_connection = real_connection
        self._counters = {"update_calls": 0}

    def cursor(self):
        return _FailOnSecondUpdateCursor(self.real_connection.cursor(), self._counters)

    def commit(self):
        self.real_connection.commit()

    def rollback(self):
        self.real_connection.rollback()

    @property
    def autocommit(self):
        return self.real_connection.autocommit

    @autocommit.setter
    def autocommit(self, value):
        self.real_connection.autocommit = value


def test_a_new_user_starts_at_the_default_rating():
    user_store, rating_store = _make_stores()
    user_store.create_or_verify("alice", "hunter2")

    assert rating_store.get_rating("alice") == 1200


def test_update_ratings_for_equal_ratings_and_a_white_win():
    user_store, rating_store = _make_stores()
    user_store.create_or_verify("alice", "pw")
    user_store.create_or_verify("bob", "pw")

    new_white, new_black = rating_store.update_ratings("alice", "bob", "white")

    # Hand-computed: K=32, expected=0.5 each at equal rating 1200.
    # white: 1200 + 32*(1 - 0.5) = 1216, black: 1200 + 32*(0 - 0.5) = 1184.
    assert (new_white, new_black) == (1216, 1184)
    assert rating_store.get_rating("alice") == 1216
    assert rating_store.get_rating("bob") == 1184


def test_update_ratings_for_equal_ratings_and_a_draw():
    user_store, rating_store = _make_stores()
    user_store.create_or_verify("alice", "pw")
    user_store.create_or_verify("bob", "pw")

    new_white, new_black = rating_store.update_ratings("alice", "bob", None)

    # Hand-computed: equal ratings, draw score 0.5 each - no change.
    assert (new_white, new_black) == (1200, 1200)


def test_update_ratings_rolls_back_both_rows_if_the_second_update_fails():
    user_store, rating_store = _make_stores()
    user_store.create_or_verify("alice", "pw")
    user_store.create_or_verify("bob", "pw")

    rating_store._connection = _ConnectionThatFailsSecondUpdate(rating_store._connection)

    with pytest.raises(RuntimeError):
        rating_store.update_ratings("alice", "bob", "white")

    # Swap back to the real connection to inspect the persisted state without the wrapper.
    rating_store._connection = rating_store._connection.real_connection
    assert rating_store.get_rating("alice") == 1200  # white's UPDATE was rolled back too
    assert rating_store.get_rating("bob") == 1200

    # autocommit must be restored too, or every later query on this connection
    # (get_rating, create_or_verify) would sit idle-in-transaction indefinitely.
    assert rating_store._connection.autocommit is True


def test_update_ratings_for_an_unequal_upset_favors_the_underdog():
    user_store, rating_store = _make_stores()
    user_store.create_or_verify("alice", "pw")
    user_store.create_or_verify("bob", "pw")
    # Seed an unequal starting point directly, rather than getting there
    # via prior game results - keeps this test's expected values a
    # direct, independent hand-computation from a known starting rating.
    with rating_store._connection.cursor() as cursor:
        cursor.execute("UPDATE users SET rating = %s WHERE username = %s", (1400, "alice"))
        cursor.execute("UPDATE users SET rating = %s WHERE username = %s", (1000, "bob"))
    rating_store._connection.commit()

    new_white, new_black = rating_store.update_ratings("alice", "bob", "black")

    # Hand-computed: expected(white)=1/(1+10**(-400/400))=0.9091,
    # expected(black)=0.0909. white (lost, favorite): 1400+32*(0-0.9091)
    # = 1371. black (won, underdog): 1000+32*(1-0.0909) = 1029.
    assert (new_white, new_black) == (1371, 1029)
