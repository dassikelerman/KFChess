import pytest

from server.contracts import Participant
from server.matchmaker import AlreadyQueuedError, MatchFound, MatchQueued, Matchmaker


def _make_client(label, rating):
    return Participant(connection=f"conn-{label}", username=label, rating=rating)


def test_a_client_with_a_compatible_rating_is_matched_against_the_waiting_client():
    matchmaker = Matchmaker()
    alice = _make_client("alice", 1200)
    bob = _make_client("bob", 1250)

    queued = matchmaker.enqueue_or_match(alice)
    assert isinstance(queued, MatchQueued)
    assert queued.participant is alice

    found = matchmaker.enqueue_or_match(bob)
    assert isinstance(found, MatchFound)
    assert found.white is alice
    assert found.black is bob


def test_an_incompatible_rating_stays_queued_instead_of_matching():
    matchmaker = Matchmaker()
    alice = _make_client("alice", 1200)
    carol = _make_client("carol", 1500)

    matchmaker.enqueue_or_match(alice)
    result = matchmaker.enqueue_or_match(carol)

    assert isinstance(result, MatchQueued)
    assert result.participant is carol


def test_the_earliest_compatible_waiter_becomes_white():
    matchmaker = Matchmaker()
    alice = _make_client("alice", 1200)
    bob = _make_client("bob", 1400)
    carol = _make_client("carol", 1250)

    assert isinstance(matchmaker.enqueue_or_match(alice), MatchQueued)
    assert isinstance(matchmaker.enqueue_or_match(bob), MatchQueued)  # incompatible with alice (diff=200)
    found = matchmaker.enqueue_or_match(carol)  # compatible with alice (diff=50), not bob (diff=150)

    assert isinstance(found, MatchFound)
    assert found.white is alice
    assert found.black is carol


def test_a_duplicate_enqueue_from_the_same_client_is_rejected():
    matchmaker = Matchmaker()
    alice = _make_client("alice", 1200)
    matchmaker.enqueue_or_match(alice)

    with pytest.raises(AlreadyQueuedError):
        matchmaker.enqueue_or_match(alice)


def test_cancel_search_drops_a_queued_entry_so_it_is_no_longer_matchable():
    matchmaker = Matchmaker()
    alice = _make_client("alice", 1200)
    bob = _make_client("bob", 1210)
    matchmaker.enqueue_or_match(alice)

    matchmaker.cancel_search(alice)

    result = matchmaker.enqueue_or_match(bob)
    assert isinstance(result, MatchQueued)


def test_cancel_search_on_a_client_that_was_never_queued_does_not_raise():
    matchmaker = Matchmaker()
    alice = _make_client("alice", 1200)

    matchmaker.cancel_search(alice)  # must not raise


def test_tick_does_not_touch_a_real_clock():
    # No time.monotonic, no injected clock object anywhere on the instance -
    # elapsed time is purely whatever tick(dt_ms) is handed.
    matchmaker = Matchmaker()
    assert not hasattr(matchmaker, "_clock")


def test_expire_waiting_entries_removes_entries_older_than_sixty_seconds():
    matchmaker = Matchmaker()
    alice = _make_client("alice", 1200)
    matchmaker.enqueue_or_match(alice)

    assert matchmaker.tick(60_000) == []

    expired = matchmaker.tick(100)  # crosses the 60s mark
    assert [e.participant for e in expired] == [alice]


def test_an_expired_entry_is_returned_at_most_once():
    matchmaker = Matchmaker()
    alice = _make_client("alice", 1200)
    matchmaker.enqueue_or_match(alice)

    first = matchmaker.tick(61_000)
    second = matchmaker.tick(1_000)

    assert [e.participant for e in first] == [alice]
    assert second == []


def test_an_entry_still_within_the_expiry_window_is_not_expired():
    matchmaker = Matchmaker()
    alice = _make_client("alice", 1200)
    bob = _make_client("bob", 1500)
    matchmaker.enqueue_or_match(alice)

    matchmaker.tick(30_000)
    matchmaker.enqueue_or_match(bob)
    expired = matchmaker.tick(31_000)  # alice: 61s total, bob: 31s total

    assert [e.participant for e in expired] == [alice]
    # bob joined 31s later and hasn't hit the 60s window yet - still queued
    with pytest.raises(AlreadyQueuedError):
        matchmaker.enqueue_or_match(bob)


def test_a_single_large_tick_still_expires_an_entry_that_has_been_waiting_too_long():
    # Large dt_ms values (e.g. after a slow server tick) must not be missed just
    # because there was no tick exactly at the expiry boundary.
    matchmaker = Matchmaker()
    alice = _make_client("alice", 1200)
    matchmaker.enqueue_or_match(alice)

    expired = matchmaker.tick(5 * 60_000)

    assert [e.participant for e in expired] == [alice]
