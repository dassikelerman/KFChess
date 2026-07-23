"""Home-screen wire messages: login, matchmaking, and private rooms.

Everything a client exchanges with the server before (or instead of) being seated in a
game - see game_messages.py for the in-game MoveIntent/JumpIntent.
"""

from dataclasses import dataclass

from protocol.message_types import RoomAction
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


register("Login", Login, _login_fields, _login_kwargs)
register("LoggedIn", LoggedIn, _logged_in_fields, _logged_in_kwargs)
register("PlayIntent", PlayIntent, _play_intent_fields, _play_intent_kwargs)
register("RoomIntent", RoomIntent, _room_intent_fields, _room_intent_kwargs)
register("RoomCreated", RoomCreated, _room_created_fields, _room_created_kwargs)
register("RoomRejected", RoomRejected, _room_rejected_fields, _room_rejected_kwargs)
register("MatchNotFound", MatchNotFound, _match_not_found_fields, _match_not_found_kwargs)
