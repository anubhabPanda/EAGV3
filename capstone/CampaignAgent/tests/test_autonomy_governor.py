"""Bounds on an agent nobody is watching, and the visibility of every refusal.

Each test here corresponds to a way an unattended agent gets into trouble that a
supervised one does not: it answers itself, it is used as a spending weapon by
whoever can create an event, it walks around a per-run ceiling by starting more
runs, it pays to be awake without anybody counting, or it dies quietly and looks
exactly like a peaceful night.
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest

from sourcecode.events import (
    AutonomousEventEngine,
    AutonomyGovernor,
    EventEnvelope,
    EventStore,
    Subscription,
    liveness_status,
    morning_report,
)


def _event(**changes) -> EventEnvelope:
    body = {"id": "e1", "source": "deployments", "type": "deployment.completed",
            "subject": "checkout/production", "occurred_at": datetime.now(UTC),
            "data": {"previous_error_rate": 0.7, "current_error_rate": 6.4}}
    body.update(changes)
    return EventEnvelope(**body)


def _subscription(**changes) -> Subscription:
    body = {"id": "watch", "instruction": "Assess material error-rate increases.",
            "event_types": ["deployment.completed"], "sources": ["deployments"],
            "tenant_id": "course", "allowed_side_effects": [], "budget": 0.02}
    body.update(changes)
    return Subscription(**body)


class _Runtime:
    """A runtime that records whether it was ever asked to do work."""

    def __init__(self, spend: float = 0.001) -> None:
        self.runs: list[str] = []
        self.spend = spend

    async def run(self, *, prompt: str, **_: object) -> dict[str, object]:
        self.runs.append(prompt)
        return {"run_id": f"run-{len(self.runs)}", "status": "completed", "spend_usd": self.spend}


def _relevance_llm(relevant: bool = True, cost: float = 0.00002):
    async def llm(prompt: str, system: str):  # noqa: ARG001
        return {"text": json.dumps({"relevant": relevant, "reason": "error rate rose",
                                    "goal": "Assess the increase." if relevant else ""}),
                "metered_calls": [{"cost_usd": cost}]}
    return llm


# ---------------------------------------------------------------- self-trigger


async def test_an_agent_refuses_an_event_it_caused_itself(tmp_path) -> None:
    """The loop that a spend ceiling only ends after the money is gone."""
    store = EventStore(tmp_path)
    runtime = _Runtime()
    engine = AutonomousEventEngine(store, runtime,
                                   governor=AutonomyGovernor(store, self_actors=("sourcecode",)))
    store.put_subscription(_subscription())

    outcome = await engine.process(_event(actor="sourcecode"), llm=_relevance_llm())

    assert outcome["refused"] is True
    assert outcome["control"] == "self_trigger"
    assert runtime.runs == []
    # And the refusal is visible, rather than looking like a quiet minute.
    assert [item["control"] for item in store.refusals()] == ["self_trigger"]


async def test_an_event_from_somebody_else_is_unaffected(tmp_path) -> None:
    store = EventStore(tmp_path)
    runtime = _Runtime()
    engine = AutonomousEventEngine(store, runtime,
                                   governor=AutonomyGovernor(store, self_actors=("sourcecode",)))
    store.put_subscription(_subscription())

    outcome = await engine.process(_event(actor="ci-server"), llm=_relevance_llm())
    assert outcome["accepted"] is True
    assert runtime.runs


# ------------------------------------------------------------- source flooding


async def test_a_flooding_source_is_rate_limited_before_it_costs_anything(tmp_path) -> None:
    """Anyone who can create an event can schedule this agent. Bound it."""
    store = EventStore(tmp_path)
    runtime = _Runtime()
    engine = AutonomousEventEngine(
        store, runtime, governor=AutonomyGovernor(store, source_events_per_minute=3))
    store.put_subscription(_subscription())
    llm = _relevance_llm()

    outcomes = [await engine.process(_event(id=f"e{index}"), llm=llm) for index in range(6)]

    admitted = [item for item in outcomes if item.get("accepted")]
    refused = [item for item in outcomes if item.get("refused")]
    assert len(admitted) == 3
    assert len(refused) == 3
    assert {item["control"] for item in refused} == {"source_rate_limit"}
    assert len(runtime.runs) == 3


# ------------------------------------------------------- the cost of being awake


async def test_triage_spend_is_metered_even_when_nothing_is_relevant(tmp_path) -> None:
    """Deciding not to act is not free, and the bill has to land somewhere."""
    store = EventStore(tmp_path)
    engine = AutonomousEventEngine(store, _Runtime())
    store.put_subscription(_subscription())

    await engine.process(_event(id="quiet-1"), llm=_relevance_llm(relevant=False, cost=0.00003))

    day = datetime.now(UTC).date().isoformat()
    assert store.window_count("watch", day, kind="triage") == 1
    assert store.window_spend("watch", day, kind="triage") == pytest.approx(0.00003)
    assert store.window_count("watch", day, kind="run") == 0


async def test_the_triage_ceiling_stops_the_gate_itself(tmp_path) -> None:
    """The control that prevents denial-of-wallet must not be the unmetered surface."""
    store = EventStore(tmp_path)
    runtime = _Runtime()
    engine = AutonomousEventEngine(store, runtime)
    store.put_subscription(_subscription(daily_triage_budget=0.00005))
    llm = _relevance_llm(relevant=False, cost=0.00003)

    calls = []

    async def counting(prompt: str, system: str):
        calls.append(prompt)
        return await llm(prompt, system)

    for index in range(5):
        await engine.process(_event(id=f"awake-{index}"), llm=counting)

    # Two calls fit inside the ceiling; the rest are refused without a model call.
    assert len(calls) == 2
    assert any(item["control"] == "daily_triage_budget" for item in store.refusals())


# -------------------------------------------------------------- the window bound


async def test_a_daily_run_ceiling_bounds_an_agent_that_starts_its_own_runs(tmp_path) -> None:
    """A per-run ceiling does not bound a caller who can start more runs."""
    store = EventStore(tmp_path)
    runtime = _Runtime()
    engine = AutonomousEventEngine(store, runtime)
    store.put_subscription(_subscription(max_runs_per_day=2))
    llm = _relevance_llm()

    for index in range(5):
        await engine.process(_event(id=f"run-{index}"), llm=llm)

    assert len(runtime.runs) == 2
    refusals = [item for item in store.refusals() if item["control"] == "max_runs_per_day"]
    assert len(refusals) == 3


async def test_a_daily_budget_caps_the_window_and_shrinks_the_last_run(tmp_path) -> None:
    store = EventStore(tmp_path)
    runtime = _Runtime(spend=0.004)
    engine = AutonomousEventEngine(store, runtime)
    store.put_subscription(_subscription(budget=0.01, daily_budget=0.01))
    llm = _relevance_llm()

    for index in range(6):
        await engine.process(_event(id=f"spend-{index}"), llm=llm)

    day = datetime.now(UTC).date().isoformat()
    assert store.window_spend("watch", day, kind="run") == pytest.approx(0.012)
    assert len(runtime.runs) == 3  # the fourth is refused: the window is exhausted
    assert any(item["control"] == "daily_budget" for item in store.refusals())


# -------------------------------------------------------------------- liveness


def test_a_quiet_night_and_a_dead_watcher_do_not_look_the_same(tmp_path) -> None:
    store = EventStore(tmp_path)

    silent = liveness_status(store)
    assert silent["alive"] is False
    assert "no heartbeat" in silent["reason"]

    store.beat(note="tick")
    assert liveness_status(store)["alive"] is True

    # Same store, same absence of work, one meaningful difference: no beat.
    later = datetime.now(UTC) + timedelta(seconds=1_200)
    dead = liveness_status(store, now=later, stale_after=900)
    assert dead["alive"] is False
    assert "may have died" in dead["reason"]


# ----------------------------------------------------------- the morning report


async def test_the_report_separates_watching_from_doing_and_shows_what_was_ignored(tmp_path) -> None:
    store = EventStore(tmp_path)
    runtime = _Runtime(spend=0.002)
    engine = AutonomousEventEngine(store, runtime)
    store.put_subscription(_subscription())

    await engine.process(_event(id="acted"), llm=_relevance_llm(relevant=True, cost=0.00001))
    await engine.process(_event(id="ignored"), llm=_relevance_llm(relevant=False, cost=0.00001))

    report = morning_report(store)
    assert report["totals"]["events_seen"] == 2
    assert report["totals"]["acted"] == 1
    assert report["totals"]["ignored"] == 1
    # The two bills the session insists on separating.
    assert report["totals"]["cost_of_watching_usd"] == pytest.approx(0.00002)
    assert report["totals"]["cost_of_doing_usd"] == pytest.approx(0.002)
    assert report["ignored"][0]["reason"]


async def test_the_report_counts_each_refusal_exactly_once(tmp_path) -> None:
    """"What a rule stopped" is the number an operator reads to tell a
    well-defended night from an idle one. A governor refusal is written to two
    places by design — a per-event decision (so it shows next to the event) and
    the refusals ledger (so it is visible even when the body is compacted away).
    The report must reconcile those two views, not sum them, or a single blocked
    run reads as two and the operator over-counts the threat.
    """
    store = EventStore(tmp_path)
    runtime = _Runtime()
    engine = AutonomousEventEngine(store, runtime)
    store.put_subscription(_subscription(max_runs_per_day=1))
    llm = _relevance_llm()

    # Three relevant events, one run allowed, two refused by the window ceiling.
    for index in range(3):
        await engine.process(_event(id=f"run-{index}"), llm=llm)

    assert len(runtime.runs) == 1
    ledger = [item for item in store.refusals() if item["control"] == "max_runs_per_day"]
    assert len(ledger) == 2  # the ground truth: exactly two runs were blocked

    report = morning_report(store)
    assert report["totals"]["acted"] == 1
    # The two blocked runs must be counted once, not once per storage location.
    assert report["totals"]["blocked_by_a_control"] == 2
    refused_keys = [(item.get("event"), item.get("control")) for item in report["refused"]]
    assert len(refused_keys) == 2
    assert len(set(refused_keys)) == 2  # and no duplicate rows


# ------------------------------------------------------- history and identity


def test_a_compacted_history_still_refuses_a_duplicate(tmp_path) -> None:
    """Forgetting a body loses history; forgetting an id repeats work."""
    store = EventStore(tmp_path, history_limit=3)
    for index in range(6):
        store.ingest(_event(id=f"e{index}"))

    retained = store.events()
    assert len(retained) == 3
    assert store.liveness()["compacted_before"] > 0

    record, fresh = store.ingest(_event(id="e0"))  # body long gone
    assert fresh is False
    assert record.get("compacted") is True


class _SlowRuntime(_Runtime):
    """A runtime that takes long enough for a second decider to interleave."""

    async def run(self, *, prompt: str, **_: object) -> dict[str, object]:
        self.runs.append(prompt)
        await asyncio.sleep(0.02)
        return {"run_id": f"run-{len(self.runs)}", "status": "completed", "spend_usd": self.spend}


async def test_the_run_ceiling_holds_when_events_arrive_together(tmp_path) -> None:
    """The ceiling has to hold for concurrent arrivals, not just a for-loop.

    The count is read at admission and written after the run, with an `await`
    in between, so several deciders can read the same pre-run number and each
    conclude there is room. That is the case the governor exists for: an agent
    woken by a stream of events, where the arrivals are exactly what is being
    bounded.
    """
    store = EventStore(tmp_path)
    runtime = _SlowRuntime()
    engine = AutonomousEventEngine(store, runtime, max_concurrent=4)
    store.put_subscription(_subscription(max_runs_per_day=1))
    llm = _relevance_llm()

    await asyncio.gather(*(engine.process(_event(id=f"burst-{i}"), llm=llm) for i in range(4)))

    day = datetime.now(UTC).date().isoformat()
    assert len(runtime.runs) == 1, "the ceiling is 1; concurrent arrivals must not walk around it"
    assert store.window_count("watch", day, kind="run") == 1
    refusals = [item for item in store.refusals() if item["control"] == "max_runs_per_day"]
    assert len(refusals) == 3, "each refusal must leave a trace, not just not happen"


async def test_a_run_refused_for_money_does_not_consume_a_run_slot(tmp_path) -> None:
    """Admission claims a slot, so it must not claim one on the way to a refusal."""
    store = EventStore(tmp_path)
    runtime = _Runtime(spend=0.004)
    engine = AutonomousEventEngine(store, runtime)
    store.put_subscription(_subscription(budget=0.01, daily_budget=0.008, max_runs_per_day=10))
    llm = _relevance_llm()

    for index in range(4):
        await engine.process(_event(id=f"money-{index}"), llm=llm)

    day = datetime.now(UTC).date().isoformat()
    assert any(item["control"] == "daily_budget" for item in store.refusals())
    # Two runs happened; the budget refusals after them must not have counted.
    assert store.window_count("watch", day, kind="run") == len(runtime.runs)
