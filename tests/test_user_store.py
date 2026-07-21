from server.user_store import DEFAULT_RATING, UserStore


def make_store(tmp_path):
    return UserStore(str(tmp_path / "test_users.db"))


def test_a_new_username_is_created(tmp_path):
    store = make_store(tmp_path)

    assert store.create_or_verify("alice", "hunter2") == "created"


def test_an_existing_username_with_the_correct_password_is_authenticated(tmp_path):
    store = make_store(tmp_path)
    store.create_or_verify("alice", "hunter2")

    assert store.create_or_verify("alice", "hunter2") == "authenticated"


def test_an_existing_username_with_the_wrong_password_is_rejected(tmp_path):
    store = make_store(tmp_path)
    store.create_or_verify("alice", "hunter2")

    assert store.create_or_verify("alice", "wrong-password") == "wrong_password"


def test_passwords_are_never_stored_in_plain_text(tmp_path):
    store = make_store(tmp_path)
    store.create_or_verify("alice", "hunter2")

    row = store._connection.execute(
        "SELECT password_hash, password_salt FROM users WHERE username = ?", ("alice",),
    ).fetchone()
    password_hash, salt = row
    assert "hunter2" not in password_hash
    assert password_hash != "hunter2"
    assert salt  # a real per-user salt was generated


def test_a_new_user_starts_at_the_default_rating(tmp_path):
    store = make_store(tmp_path)
    store.create_or_verify("alice", "hunter2")

    assert store.get_rating("alice") == DEFAULT_RATING == 1200


def test_update_ratings_for_equal_ratings_and_a_white_win(tmp_path):
    store = make_store(tmp_path)
    store.create_or_verify("alice", "pw")
    store.create_or_verify("bob", "pw")

    new_white, new_black = store.update_ratings("alice", "bob", "white")

    # Hand-computed: K=32, expected=0.5 each at equal rating 1200.
    # white: 1200 + 32*(1 - 0.5) = 1216, black: 1200 + 32*(0 - 0.5) = 1184.
    assert (new_white, new_black) == (1216, 1184)
    assert store.get_rating("alice") == 1216
    assert store.get_rating("bob") == 1184


def test_update_ratings_for_equal_ratings_and_a_draw(tmp_path):
    store = make_store(tmp_path)
    store.create_or_verify("alice", "pw")
    store.create_or_verify("bob", "pw")

    new_white, new_black = store.update_ratings("alice", "bob", None)

    # Hand-computed: equal ratings, draw score 0.5 each - no change.
    assert (new_white, new_black) == (1200, 1200)


def test_update_ratings_for_an_unequal_upset_favors_the_underdog(tmp_path):
    store = make_store(tmp_path)
    store.create_or_verify("alice", "pw")
    store.create_or_verify("bob", "pw")
    # Seed an unequal starting point directly, rather than getting there
    # via prior game results - keeps this test's expected values a
    # direct, independent hand-computation from a known starting rating.
    store._connection.execute("UPDATE users SET rating = ? WHERE username = ?", (1400, "alice"))
    store._connection.execute("UPDATE users SET rating = ? WHERE username = ?", (1000, "bob"))
    store._connection.commit()

    new_white, new_black = store.update_ratings("alice", "bob", "black")

    # Hand-computed: expected(white)=1/(1+10**(-400/400))=0.9091,
    # expected(black)=0.0909. white (lost, favorite): 1400+32*(0-0.9091)
    # = 1371. black (won, underdog): 1000+32*(1-0.0909) = 1029.
    assert (new_white, new_black) == (1371, 1029)
