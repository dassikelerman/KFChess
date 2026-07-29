from tests.db_helpers import reset_users_table

from server.user_store import LoginResult, UserStore


def make_store():
    reset_users_table()
    return UserStore()


def test_a_new_username_is_created():
    store = make_store()

    assert store.create_or_verify("alice", "hunter2") is LoginResult.CREATED


def test_an_existing_username_with_the_correct_password_is_authenticated():
    store = make_store()
    store.create_or_verify("alice", "hunter2")

    assert store.create_or_verify("alice", "hunter2") is LoginResult.AUTHENTICATED


def test_an_existing_username_with_the_wrong_password_is_rejected():
    store = make_store()
    store.create_or_verify("alice", "hunter2")

    assert store.create_or_verify("alice", "wrong-password") is LoginResult.WRONG_PASSWORD


def test_passwords_are_never_stored_in_plain_text():
    store = make_store()
    store.create_or_verify("alice", "hunter2")

    with store._connection.cursor() as cursor:
        cursor.execute("SELECT password_hash, password_salt FROM users WHERE username = %s", ("alice",))
        password_hash, salt = cursor.fetchone()
    assert "hunter2" not in password_hash
    assert password_hash != "hunter2"
    assert salt  # a real per-user salt was generated
