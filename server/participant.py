"""Participant: everything the server tracks about one connected participant.

Shared, no-behavior vocabulary - a plain data record, not owned by any single file.
ConnectionLifecycle fills in the auth fields as a connection logs in, GameRoomRegistry
fills in the room/role fields once it's seated, and ClientMessageRouter only ever reads
`.state` to decide whether a message is currently allowed. A participant starts as just
a connection and, over its life, becomes a player or a spectator - the name describes
where it ends up, not just the wire it arrived on.
"""

import secrets
from dataclasses import dataclass, field
from enum import Enum, auto


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
