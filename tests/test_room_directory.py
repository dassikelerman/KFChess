import redis

from server.room_directory import DEFAULT_REDIS_URL, AlreadyInRoomError, RoomDirectory
from tests.redis_helpers import flush_directory


def _make_directory(game_server_id="shard-a"):
    flush_directory()
    directory = RoomDirectory(game_server_id)
    # Mirrors real usage: GameRoomRegistry always refreshes its own shard's heartbeat
    # immediately at construction (see rooms.py) - a directory whose shard never
    # heartbeats looks dead to every lookup by design (see the dedicated tests below).
    directory.refresh_heartbeat()
    return directory


def test_reserve_new_room_claims_the_room_and_every_username():
    directory = _make_directory()

    status = directory.reserve_new_room("room-1", ["alice", "bob"])

    assert status == "ok"
    assert directory.get_room_owner("room-1") == "shard-a"
    assert directory.get_room_for_username("alice") == "room-1"
    assert directory.get_room_for_username("bob") == "room-1"


def test_reserve_new_room_with_a_join_code_claims_that_too():
    directory = _make_directory()

    status = directory.reserve_new_room("room-1", ["alice"], join_code="ABC123")

    assert status == "ok"
    room_id = directory.reserve_join("ABC123", "carol")
    assert room_id == "room-1"


def test_reserve_new_room_rejects_a_username_already_seated_and_writes_nothing():
    directory = _make_directory()
    directory.reserve_new_room("room-1", ["alice"])

    status = directory.reserve_new_room("room-2", ["alice", "carol"])

    assert status == "username_conflict"
    # Nothing from the failed attempt was written - not room-2, not carol.
    assert directory.get_room_owner("room-2") is None
    assert directory.get_room_for_username("carol") is None


def test_reserve_new_room_reports_an_identifier_conflict_separately_from_a_username_conflict():
    directory = _make_directory()
    directory.reserve_new_room("room-1", ["alice"])

    # room-1 is already taken, but bob is free - this must be retry-worthy (a fresh
    # room_id would succeed), not the same rejection as an already-seated username.
    status = directory.reserve_new_room("room-1", ["bob"])

    assert status == "identifier_conflict"
    assert directory.get_room_for_username("bob") is None


def test_reserve_join_resolves_the_code_and_claims_the_joiner():
    directory = _make_directory()
    directory.reserve_new_room("room-1", ["alice"], join_code="ABC123")

    room_id = directory.reserve_join("ABC123", "bob")

    assert room_id == "room-1"
    assert directory.get_room_for_username("bob") == "room-1"


def test_reserve_join_with_an_unknown_code_returns_none():
    directory = _make_directory()

    assert directory.reserve_join("NOPE99", "bob") is None


def test_reserve_join_against_an_already_closed_room_returns_none():
    directory = _make_directory()
    directory.reserve_new_room("room-1", ["alice"], join_code="ABC123")
    directory.close_room("room-1", ["alice"], join_code="ABC123")

    assert directory.reserve_join("ABC123", "bob") is None


def test_reserve_join_raises_if_the_joiner_is_already_seated_elsewhere():
    directory = _make_directory()
    directory.reserve_new_room("room-1", ["alice"], join_code="ABC123")
    directory.reserve_new_room("room-2", ["bob"])

    try:
        directory.reserve_join("ABC123", "bob")
        assert False, "expected AlreadyInRoomError"
    except AlreadyInRoomError:
        pass

    # bob's original room mapping must be untouched by the rejected join attempt.
    assert directory.get_room_for_username("bob") == "room-2"


def test_close_room_removes_the_room_every_username_and_the_join_code():
    directory = _make_directory()
    directory.reserve_new_room("room-1", ["alice", "bob"], join_code="ABC123")

    directory.close_room("room-1", ["alice", "bob"], join_code="ABC123")

    assert directory.get_room_owner("room-1") is None
    assert directory.get_room_for_username("alice") is None
    assert directory.get_room_for_username("bob") is None
    assert directory.reserve_join("ABC123", "carol") is None


def test_release_username_only_removes_that_one_mapping():
    directory = _make_directory()
    directory.reserve_new_room("room-1", ["alice", "bob"])

    directory.release_username("alice")

    assert directory.get_room_for_username("alice") is None
    assert directory.get_room_for_username("bob") == "room-1"


def test_get_room_owner_treats_a_room_under_a_dead_shard_as_gone_and_cleans_it_up():
    flush_directory()
    dead_shard = RoomDirectory("dead-shard")
    dead_shard.reserve_new_room("room-1", ["alice"])
    # dead_shard never called refresh_heartbeat(), so its shard key was never created.

    live_shard = RoomDirectory("live-shard")
    live_shard.refresh_heartbeat()

    assert live_shard.get_room_owner("room-1") is None
    # The stale entry was cleaned up as a side effect of being discovered.
    raw = redis.Redis.from_url(DEFAULT_REDIS_URL, decode_responses=True)
    assert raw.get("directory:room:room-1") is None


def test_get_room_for_username_treats_a_dead_shards_room_as_gone_and_cleans_up_the_user_entry():
    flush_directory()
    dead_shard = RoomDirectory("dead-shard-2")
    dead_shard.reserve_new_room("room-1", ["alice"])

    live_shard = RoomDirectory("live-shard-2")
    live_shard.refresh_heartbeat()

    assert live_shard.get_room_for_username("alice") is None
    raw = redis.Redis.from_url(DEFAULT_REDIS_URL, decode_responses=True)
    assert raw.get("directory:user:alice") is None


def test_refresh_heartbeat_makes_is_shard_alive_true():
    directory = _make_directory("shard-x")

    directory.refresh_heartbeat()

    assert directory.is_shard_alive("shard-x") is True
    assert directory.is_shard_alive("some-other-shard-that-never-refreshed") is False
