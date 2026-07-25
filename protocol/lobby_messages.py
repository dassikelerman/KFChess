"""Home-screen wire messages: login, matchmaking, and private rooms.

Everything a client exchanges with the server before (or instead of) being seated in a
game - see game_messages.py for the in-game MoveIntent/JumpIntent.
"""

from dataclasses import dataclass

from protocol.message_types import MessageType, RoomAction
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
class RoomIntent:
    action: RoomAction
    room_id: str | None = None


@dataclass(frozen=True)
class RoomCreated:
    room_id: str


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


def _room_intent_fields(intent):
    return {"action": intent.action.value, "room_id": intent.room_id}


def _room_intent_kwargs(data):
    action = RoomAction(data["action"])
    if action is RoomAction.JOIN:
        room_id = (data.get("room_id") or "").strip()
        if not room_id:
            raise InvalidRoomIntentError("RoomIntent(action=join) requires a non-empty room_id")
        return dict(action=action, room_id=room_id)
    # CREATE never needs a room_id - the server assigns one - so any room_id sent alongside it is ignored.
    return dict(action=action, room_id=None)


def _room_created_fields(message):
    return {"room_id": message.room_id}


def _room_created_kwargs(data):
    return dict(room_id=data["room_id"])


def _room_rejected_fields(message):
    return {"reason": message.reason}


def _room_rejected_kwargs(data):
    return dict(reason=data["reason"])


def _match_not_found_fields(message):
    return {"reason": message.reason}


def _match_not_found_kwargs(data):
    return dict(reason=data["reason"])


def _role_assigned_fields(message):
    return {"role": message.role, "room_id": message.room_id}


def _role_assigned_kwargs(data):
    return dict(role=data["role"], room_id=data["room_id"])


register(MessageType.LOGIN, Login, _login_fields, _login_kwargs)
register(MessageType.LOGGED_IN, LoggedIn, _logged_in_fields, _logged_in_kwargs)
register(MessageType.PLAY_INTENT, PlayIntent, _play_intent_fields, _play_intent_kwargs)
register(MessageType.ROOM_INTENT, RoomIntent, _room_intent_fields, _room_intent_kwargs)
register(MessageType.ROOM_CREATED, RoomCreated, _room_created_fields, _room_created_kwargs)
register(MessageType.ROOM_REJECTED, RoomRejected, _room_rejected_fields, _room_rejected_kwargs)
register(MessageType.MATCH_NOT_FOUND, MatchNotFound, _match_not_found_fields, _match_not_found_kwargs)
register(MessageType.ROLE_ASSIGNED, RoleAssigned, _role_assigned_fields, _role_assigned_kwargs)
