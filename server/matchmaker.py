"""Matchmaker: matchmaking only - a rating-aware waiting queue for the "Play" button.

A seeker is paired with the earliest still-waiting seeker within rating_tolerance, or
queued if none qualifies; a queued seeker who waits past expiry_seconds is reported as
expired on the next tick. Pure bookkeeping - it knows nothing about sockets, rooms, or
the engine, only participant objects and ratings, so it is fully unit-tested with no
network and no real time (the clock is injected).
"""

import time
from dataclasses import dataclass
from typing import Callable

import constants


@dataclass(frozen=True)
class MatchmakingEntry:
    participant: object
    username: str
    rating: int
    joined_at: float


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
        self, clock: Callable[[], float] = time.monotonic,
        rating_tolerance=constants.MATCHMAKING_RATING_TOLERANCE,
        expiry_seconds=constants.MATCHMAKING_TIMEOUT_SECONDS,
    ):
        self._clock = clock
        self._rating_tolerance = rating_tolerance
        self._expiry_seconds = expiry_seconds
        self._entries = []

    def enqueue_or_match(self, participant):
        if self._find_entry(participant) is not None:
            raise AlreadyQueuedError(f"{participant.username!r} is already queued for a match")

        opponent = self._find_earliest_compatible(participant.rating)
        if opponent is not None:
            self._entries.remove(opponent)
            return MatchFound(white=opponent.participant, black=participant)

        entry = MatchmakingEntry(
            participant=participant, username=participant.username, rating=participant.rating,
            joined_at=self._clock(),
        )
        self._entries.append(entry)
        return MatchQueued(participant)

    def expire_waiting_entries(self):
        now = self._clock()
        expired = [entry for entry in self._entries if now - entry.joined_at > self._expiry_seconds]
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
