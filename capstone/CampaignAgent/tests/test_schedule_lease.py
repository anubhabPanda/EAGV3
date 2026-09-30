"""A periodic trigger must not overlap itself, and a skip must be a decision."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sourcecode.events import ScheduleLease


def test_a_second_tick_cannot_run_while_the_first_still_holds_the_lease(tmp_path) -> None:
    lease = ScheduleLease(tmp_path, ttl_seconds=900)

    first = lease.acquire("nightly-sweep", holder="tick-0900")
    assert first.granted is True

    second = lease.acquire("nightly-sweep", holder="tick-0905")
    assert second.granted is False
    assert "still running" in second.reason
    assert second.holder == "tick-0900"


def test_releasing_lets_the_next_tick_run(tmp_path) -> None:
    lease = ScheduleLease(tmp_path)
    first = lease.acquire("sweep", holder="a")
    assert lease.release("sweep", first.token) is True
    assert lease.acquire("sweep", holder="b").granted is True


def test_only_the_holder_may_release(tmp_path) -> None:
    """A restarted process must not be able to unlock work still in flight."""
    lease = ScheduleLease(tmp_path)
    lease.acquire("sweep", holder="a")
    assert lease.release("sweep", "some-other-token") is False
    assert lease.acquire("sweep", holder="b").granted is False


def test_an_expired_lease_is_stolen_and_the_theft_is_recorded(tmp_path) -> None:
    """A holder that crashed must not lock the schedule forever."""
    lease = ScheduleLease(tmp_path, ttl_seconds=60)
    start = datetime.now(UTC)
    lease.acquire("sweep", holder="crashed-worker", now=start)

    later = start + timedelta(seconds=120)
    recovered = lease.acquire("sweep", holder="fresh-worker", now=later)
    assert recovered.granted is True
    assert "expired lease" in recovered.reason
    assert lease.state("sweep")["stolen_from"] == "crashed-worker"


def test_leases_are_keyed_by_schedule_not_by_process(tmp_path) -> None:
    lease = ScheduleLease(tmp_path)
    assert lease.acquire("sweep-a", holder="w").granted is True
    assert lease.acquire("sweep-b", holder="w").granted is True
    assert lease.acquire("sweep-a", holder="w").granted is False
