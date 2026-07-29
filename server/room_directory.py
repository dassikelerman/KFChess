"""RoomDirectory: Redis-backed room/user/join-code routing metadata.

Three mappings, all pure routing/discovery metadata - never the live game state itself
(GameSession, connections, Participants all stay local to whichever Game Server process
actually hosts them; see server/rooms.py):

    directory:room:{room_id}   -> game_server_id   (which shard hosts this room)
    directory:user:{username}  -> room_id           (which room, if any, a user occupies)
    directory:join:{join_code} -> room_id           (a private room's human-typable code)

Each entry is written once at creation and removed once at _close_room - none of them
is ever updated in place. Creating a room touches more than one key at once (the room
entry plus one entry per seated username, and a join code for private rooms) and a
partial write there would leave a username falsely marked "in a room" with no room to
match - so those writes go through a Lua script, atomic because Redis executes it as a
single, uninterruptible unit. Deleting is different: a partial delete only ever leaves
a dangling pointer that fails safe (a lookup against a half-deleted room correctly
reports "gone"), so plain multi-key DEL is enough - no script needed there.

Refreshing a TTL per room/user would be O(rooms), which the numbers in Server_Design.md
rule out. Instead, each Game Server process refreshes one heartbeat key for itself -
O(shards). Room/user/join-code entries get a long, one-time TTL as a last-resort
backstop only; the real staleness signal is whether the shard they point to is still
heartbeating, checked lazily by whichever lookup discovers a dead one.
"""

import logging
import os

import redis

import constants

logger = logging.getLogger(__name__)

DEFAULT_REDIS_URL = os.environ.get("KFCHESS_REDIS_URL", "redis://localhost:6379/0")


class AlreadyInRoomError(Exception):
    """A username is already seated in a room somewhere in the Directory."""


def _room_key(room_id):
    return f"directory:room:{room_id}"


def _user_key(username):
    return f"directory:user:{username}"


def _join_key(join_code):
    return f"directory:join:{join_code}"


def _shard_key(game_server_id):
    return f"directory:shard:{game_server_id}:alive"


# KEYS[1 .. n_identifiers] = room key, and (for a private room) the join-code key -
# collide => retry with a fresh random value. KEYS[n_identifiers+1 ..] = one entry per
# username to claim for room_id - collide => that user is genuinely seated elsewhere,
# do not retry. n_identifiers (1 or 2) is passed explicitly in ARGV[1] rather than
# padding KEYS with a placeholder key for "no join code": there is no such thing as an
# empty-string key here, only a KEYS list that is actually one or two entries long.
# ARGV[2] = game_server_id, ARGV[3] = room_id, ARGV[4] = ttl_seconds. All-or-nothing -
# nothing is written unless every check passes.
_RESERVE_NEW_ROOM_SCRIPT = """
local n_identifiers = tonumber(ARGV[1])
local ttl = tonumber(ARGV[4])

for i = 1, n_identifiers do
    if redis.call('EXISTS', KEYS[i]) == 1 then
        return 'identifier_conflict'
    end
end
for i = n_identifiers + 1, #KEYS do
    if redis.call('EXISTS', KEYS[i]) == 1 then
        return 'username_conflict'
    end
end

redis.call('SET', KEYS[1], ARGV[2], 'EX', ttl)
for i = 2, n_identifiers do
    redis.call('SET', KEYS[i], ARGV[3], 'EX', ttl)
end
for i = n_identifiers + 1, #KEYS do
    redis.call('SET', KEYS[i], ARGV[3], 'EX', ttl)
end
return 'ok'
"""

# KEYS[1] = join-code key, KEYS[2] = joining username's key. ARGV[1] = ttl_seconds.
# Resolves the join code, confirms the room it points to still exists, and only then
# claims the username - all inside one atomic step so a room closing mid-lookup can't
# leave the joiner claimed against a room that no longer exists.
_RESERVE_JOIN_SCRIPT = """
local join_key = KEYS[1]
local user_key = KEYS[2]
local ttl = tonumber(ARGV[1])

local room_id = redis.call('GET', join_key)
if not room_id then
    return {'not_found', ''}
end

if redis.call('EXISTS', 'directory:room:' .. room_id) == 0 then
    return {'not_found', ''}
end

if redis.call('EXISTS', user_key) == 1 then
    return {'already_in_room', ''}
end

redis.call('SET', user_key, room_id, 'EX', ttl)
return {'ok', room_id}
"""


class RoomDirectory:
    def __init__(self, game_server_id, redis_url=DEFAULT_REDIS_URL):
        self._game_server_id = game_server_id
        self._redis = redis.Redis.from_url(redis_url, decode_responses=True)
        self._reserve_new_room_script = self._redis.register_script(_RESERVE_NEW_ROOM_SCRIPT)
        self._reserve_join_script = self._redis.register_script(_RESERVE_JOIN_SCRIPT)

    # -- creation / joining ---------------------------------------------------

    def reserve_new_room(self, room_id, usernames, join_code=None):
        """Atomically claims room_id and every username (and join_code, if given) for
        it, or none of them. Returns 'ok', 'identifier_conflict' (retry with a fresh
        room_id/join_code), or 'username_conflict' (do not retry - someone is already
        seated)."""
        identifier_keys = [_room_key(room_id)]
        if join_code is not None:
            identifier_keys.append(_join_key(join_code))
        keys = identifier_keys + [_user_key(username) for username in usernames]
        return self._reserve_new_room_script(
            keys=keys,
            args=[len(identifier_keys), self._game_server_id, room_id, constants.DIRECTORY_KEY_TTL_SECONDS],
        )

    def reserve_join(self, join_code, username):
        """Resolves join_code and claims username for the room it points to. Returns
        the room_id on success, or None if the code (or the room it pointed to) no
        longer exists. Raises AlreadyInRoomError if username is already seated
        somewhere else."""
        status, room_id = self._reserve_join_script(
            keys=[_join_key(join_code), _user_key(username)], args=[constants.DIRECTORY_KEY_TTL_SECONDS],
        )
        if status == "not_found":
            return None
        if status == "already_in_room":
            raise AlreadyInRoomError(f"{username!r} is already seated in a room")
        return room_id

    # -- cleanup ----------------------------------------------------------------

    def close_room(self, room_id, usernames, join_code=None):
        keys = [_room_key(room_id)] + [_user_key(username) for username in usernames]
        if join_code is not None:
            keys.append(_join_key(join_code))
        self._redis.delete(*keys)

    def release_username(self, username):
        self._redis.delete(_user_key(username))

    # -- lookups, with lazy dead-shard cleanup -----------------------------------

    def get_room_owner(self, room_id):
        game_server_id = self._redis.get(_room_key(room_id))
        if game_server_id is None:
            return None
        if not self.is_shard_alive(game_server_id):
            self._redis.delete(_room_key(room_id))
            return None
        return game_server_id

    def get_room_for_username(self, username):
        room_id = self._redis.get(_user_key(username))
        if room_id is None:
            return None
        if self.get_room_owner(room_id) is None:
            self._redis.delete(_user_key(username))
            return None
        return room_id

    # -- shard heartbeat ----------------------------------------------------------

    def refresh_heartbeat(self):
        self._redis.set(_shard_key(self._game_server_id), "1", ex=constants.SHARD_HEARTBEAT_TTL_SECONDS)

    def is_shard_alive(self, game_server_id):
        return self._redis.exists(_shard_key(game_server_id)) == 1
