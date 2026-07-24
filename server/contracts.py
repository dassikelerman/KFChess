"""Shared server-side data types and Protocols - no behavior of their own.

Participant is plain data: ConnectionLifecycle fills in the auth fields as a connection
logs in, GameRoomRegistry fills in the room/role fields once it's seated, and
ClientMessageRouter only ever reads `.state` to decide whether a message is currently
allowed. A participant starts as just a connection and, over its life, becomes a player
or a spectator - the name describes where it ends up, not just the wire it arrived on.

MessageSender/RatingRepository are Protocol shapes for the handful of
GameSession/GameRoomRegistry dependencies that are genuinely swapped out in tests
(fakes) and production (the real thing) alike. Not every collaborator gets one of
these - only ones where naming the shape actually helps a reader, instead of just
reading the one concrete class that implements it.
"""

import secrets
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Protocol


class ParticipantState(Enum):
    CONNECTED = auto()
    LOBBY = auto()
    SEARCHING = auto()
    IN_ROOM = auto()
    DISCONNECTED = auto()


def _new_connection_id():
    return secrets.token_hex(4)


@dataclass
class Participant:
    connection: object
    connection_id: str = field(default_factory=_new_connection_id)
    username: str | None = None
    rating: int | None = None
    role: str | None = None
    room_id: str | None = None
    authenticated: bool = False
    state: ParticipantState = ParticipantState.CONNECTED


class MessageSender(Protocol):
    """Delivers one JSON-serializable payload dict to one connection, best-effort.

    The shared low-level send primitive: GameRoomRegistry uses it for room/game traffic
    (role assignment, snapshots, domain events), and the global server loop uses the
    same shape to push a MatchNotFound notice on matchmaking expiry. Fire-and-forget by
    contract - the real implementation (ws_server._unicast) schedules the actual write
    and swallows a closed connection instead of raising back into the caller.
    """

    def __call__(self, connection, payload: dict) -> None: ...


class RatingRepository(Protocol):
    """What GameSession needs to read and update ELO ratings. Implemented by RatingStore."""

    def get_rating(self, username: str) -> int: ...

    def update_ratings(self, white_username: str, black_username: str, winner_color: str | None): ...
