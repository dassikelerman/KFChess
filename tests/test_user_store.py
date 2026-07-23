from server.user_store import UserStore


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
