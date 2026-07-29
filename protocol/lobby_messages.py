"""Home-screen wire messages: login, matchmaking, and private rooms.

Everything a client exchanges with the server before (or instead of) being seated in a
game - see game_messages.py for the in-game MoveIntent/JumpIntent.
"""

from dataclasses import dataclass

from protocol.message_types import MessageType
from protocol.registry import register


class InvalidRoomIntentError(Exception):
    pass


@dataclass(frozen=True)
class Login:
    username: str
    password: str


@dataclass(frozen=True)
class LoggedIn:
    username: str
    rating: int


@dataclass(frozen=True)
class PlayIntent:
    pass


@dataclass(frozen=True)
class CreateRoomIntent:
    pass


@dataclass(frozen=True)
class JoinRoomIntent:
    # The short, human-typed join code shown to a private room's creator - not the
    # room's internal id (see server/room_directory.py).
    join_code: str


@dataclass(frozen=True)
class RoomRejected:
    reason: str


@dataclass(frozen=True)
class MatchNotFound:
    reason: str = "no_match_found"


@dataclass(frozen=True)
class RoleAssigned:
    role: str
    room_id: str
    # Only set for a private room's creator - the code to hand to whoever should join.
    join_code: str | None = None


def _login_fields(login):
    return {"username": login.username, "password": login.password}


def _login_kwargs(data):
    return dict(username=data["username"], password=data["password"])


def _logged_in_fields(message):
    return {"username": message.username, "rating": message.rating}


def _logged_in_kwargs(data):
    return dict(username=data["username"], rating=data["rating"])


def _play_intent_fields(intent):
    return {}


def _play_intent_kwargs(data):
    return {}


def _create_room_intent_fields(intent):
    return {}


def _create_room_intent_kwargs(data):
    return {}


def _join_room_intent_fields(intent):
    return {"join_code": intent.join_code}


def _join_room_intent_kwargs(data):
    join_code = (data.get("join_code") or "").strip()
    if not join_code:
        raise InvalidRoomIntentError("JoinRoomIntent requires a non-empty join_code")
    return dict(join_code=join_code)


def _room_rejected_fields(message):
    return {"reason": message.reason}


def _room_rejected_kwargs(data):
    return dict(reason=data["reason"])


def _match_not_found_fields(message):
    return {"reason": message.reason}


def _match_not_found_kwargs(data):
    return dict(reason=data["reason"])


def _role_assigned_fields(message):
    return {"role": message.role, "room_id": message.room_id, "join_code": message.join_code}


def _role_assigned_kwargs(data):
    return dict(role=data["role"], room_id=data["room_id"], join_code=data.get("join_code"))


register(MessageType.LOGIN, Login, _login_fields, _login_kwargs)
register(MessageType.LOGGED_IN, LoggedIn, _logged_in_fields, _logged_in_kwargs)
register(MessageType.PLAY_INTENT, PlayIntent, _play_intent_fields, _play_intent_kwargs)
register(MessageType.CREATE_ROOM_INTENT, CreateRoomIntent, _create_room_intent_fields, _create_room_intent_kwargs)
register(MessageType.JOIN_ROOM_INTENT, JoinRoomIntent, _join_room_intent_fields, _join_room_intent_kwargs)
register(MessageType.ROOM_REJECTED, RoomRejected, _room_rejected_fields, _room_rejected_kwargs)
register(MessageType.MATCH_NOT_FOUND, MatchNotFound, _match_not_found_fields, _match_not_found_kwargs)
register(MessageType.ROLE_ASSIGNED, RoleAssigned, _role_assigned_fields, _role_assigned_kwargs)
