from server.rating import RatingStore
from server.user_store import UserStore


def _make_stores(tmp_path):
    db_path = str(tmp_path / "test_users.db")
    return UserStore(db_path), RatingStore(db_path)


def test_a_new_user_starts_at_the_default_rating(tmp_path):
    user_store, rating_store = _make_stores(tmp_path)
    user_store.create_or_verify("alice", "hunter2")

    assert rating_store.get_rating("alice") == 1200


def test_update_ratings_for_equal_ratings_and_a_white_win(tmp_path):
    user_store, rating_store = _make_stores(tmp_path)
    user_store.create_or_verify("alice", "pw")
    user_store.create_or_verify("bob", "pw")

    new_white, new_black = rating_store.update_ratings("alice", "bob", "white")

    # Hand-computed: K=32, expected=0.5 each at equal rating 1200.
    # white: 1200 + 32*(1 - 0.5) = 1216, black: 1200 + 32*(0 - 0.5) = 1184.
    assert (new_white, new_black) == (1216, 1184)
    assert rating_store.get_rating("alice") == 1216
    assert rating_store.get_rating("bob") == 1184


def test_update_ratings_for_equal_ratings_and_a_draw(tmp_path):
    user_store, rating_store = _make_stores(tmp_path)
    user_store.create_or_verify("alice", "pw")
    user_store.create_or_verify("bob", "pw")

    new_white, new_black = rating_store.update_ratings("alice", "bob", None)

    # Hand-computed: equal ratings, draw score 0.5 each - no change.
    assert (new_white, new_black) == (1200, 1200)


def test_update_ratings_for_an_unequal_upset_favors_the_underdog(tmp_path):
    user_store, rating_store = _make_stores(tmp_path)
    user_store.create_or_verify("alice", "pw")
    user_store.create_or_verify("bob", "pw")
    # Seed an unequal starting point directly, rather than getting there
    # via prior game results - keeps this test's expected values a
    # direct, independent hand-computation from a known starting rating.
    rating_store._connection.execute("UPDATE users SET rating = ? WHERE username = ?", (1400, "alice"))
    rating_store._connection.execute("UPDATE users SET rating = ? WHERE username = ?", (1000, "bob"))
    rating_store._connection.commit()

    new_white, new_black = rating_store.update_ratings("alice", "bob", "black")

    # Hand-computed: expected(white)=1/(1+10**(-400/400))=0.9091,
    # expected(black)=0.0909. white (lost, favorite): 1400+32*(0-0.9091)
    # = 1371. black (won, underdog): 1000+32*(1-0.0909) = 1029.
    assert (new_white, new_black) == (1371, 1029)
