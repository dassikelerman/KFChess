"""Small Protocol shapes for the handful of GameSession/GameRoomRegistry dependencies
that are genuinely swapped out in tests (fakes) and production (the real thing) alike.
Not every collaborator gets one of these - only ones where naming the shape actually
helps a reader, instead of just reading the one concrete class that implements it.
"""

from typing import Awaitable, Protocol


class MessageSender(Protocol):
    """Delivers one JSON-serializable payload dict to one connection, best-effort.

    The shared low-level send primitive: GameRoomRegistry uses it for room/game traffic
    (role assignment, snapshots, domain events), and ws_server's matchmaking-expiry loop
    uses the same shape to push a MatchNotFound notice. Fire-and-forget by contract -
    the real implementation (ws_server._unicast) schedules the actual write and swallows
    a closed connection instead of raising back into the caller.
    """

    def __call__(self, connection, payload: dict) -> None: ...


class RatingRepository(Protocol):
    """What GameSession needs to read and update ELO ratings. Implemented by RatingStore."""

    def get_rating(self, username: str) -> int: ...

    def update_ratings(self, white_username: str, black_username: str, winner_color: str | None): ...


class Sleeper(Protocol):
    """An awaitable delay, swapped for a fake in tests so disconnect-countdown tests don't
    actually wait 20 seconds. Implemented by asyncio.sleep."""

    def __call__(self, seconds: float) -> Awaitable[None]: ...
