"""Matchmaker: matchmaking only - a rating-aware waiting queue for the "Play" button.

A seeker is paired with the earliest still-waiting seeker within rating_tolerance, or
queued if none qualifies; a queued seeker who has waited past expiry_seconds is reported
as expired on the next tick(dt_ms). Pure bookkeeping - it knows nothing about sockets,
rooms, the engine, or wall-clock time; how much time passed is simply handed to it by
the caller, so it is fully unit-tested with no network and no real sleeping.
"""

from dataclasses import dataclass

import constants


@dataclass
class MatchmakingEntry:
    participant: object
    username: str
    rating: int
    waited_ms: int = 0


@dataclass(frozen=True)
class MatchFound:
    white: object
    black: object


@dataclass(frozen=True)
class MatchQueued:
    participant: object


@dataclass(frozen=True)
class ExpiredMatch:
    participant: object


class AlreadyQueuedError(Exception):
    pass


class Matchmaker:
    def __init__(
        self, rating_tolerance=constants.MATCHMAKING_RATING_TOLERANCE,
        expiry_seconds=constants.MATCHMAKING_TIMEOUT_SECONDS,
    ):
        self._rating_tolerance = rating_tolerance
        self._expiry_ms = expiry_seconds * 1000
        self._entries = []

    def enqueue_or_match(self, participant):
        if self._find_entry(participant) is not None:
            raise AlreadyQueuedError(f"{participant.username!r} is already queued for a match")

        opponent = self._find_earliest_compatible(participant.rating)
        if opponent is not None:
            self._entries.remove(opponent)
            return MatchFound(white=opponent.participant, black=participant)

        entry = MatchmakingEntry(participant=participant, username=participant.username, rating=participant.rating)
        self._entries.append(entry)
        return MatchQueued(participant)

    def tick(self, dt_ms):
        expired = []
        for entry in self._entries:
            entry.waited_ms += dt_ms
            if entry.waited_ms > self._expiry_ms:
                expired.append(entry)

        for entry in expired:
            self._entries.remove(entry)
        return [ExpiredMatch(participant=entry.participant) for entry in expired]

    def cancel_search(self, participant):
        entry = self._find_entry(participant)
        if entry is not None:
            self._entries.remove(entry)

    def _find_entry(self, participant):
        for entry in self._entries:
            if entry.participant is participant:
                return entry
        return None

    def _find_earliest_compatible(self, rating):
        for entry in self._entries:
            if abs(entry.rating - rating) <= self._rating_tolerance:
                return entry
        return None
