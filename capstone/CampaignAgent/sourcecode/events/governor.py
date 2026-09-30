"""Bounds on unattended operation, enforced outside the agent.

Session 15 gave every *run* a hard ceiling and refused before the provider was
contacted. That ceiling stops being a ceiling the moment the agent starts its own
runs, because nothing stops it starting more of them. An agent woken by a stream
of events needs a bound over a **window**, not over one request.

Three separate things get bounded here, and they fail for different reasons:

* **Being awake.** The relevance gate is a model call on every matching event,
  forever, whether or not any work follows. It is usually the larger bill and it
  is the one nobody budgets, because it does not look like work.
* **Doing.** Runs per window and spend per window, per subscription.
* **Being used as a weapon.** Anyone who can create an event can schedule this
  agent. A per-source arrival limit turns "flood the webhook" from a spending
  attack into a recorded refusal.

And one thing gets refused outright: an event this agent itself caused. An agent
that acts in a system it also watches will see its own action arrive as a new
event. Without an actor check that is a self-sustaining loop, and a spend ceiling
only ends it after the money is gone.

Every refusal is *recorded*. Session 15 learned this the hard way: a control that
prevents work leaves no trace of the work it prevented, so an operator reading the
dashboard sees a quiet night and an untouched budget either way.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from .models import EventEnvelope, Subscription


@dataclass(frozen=True)
class Verdict:
    """The outcome of one admission check, always explainable."""

    admitted: bool
    reason: str = ""
    control: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def as_record(self) -> dict[str, Any]:
        return {"admitted": self.admitted, "reason": self.reason, "control": self.control,
                **({"detail": self.detail} if self.detail else {})}


ADMITTED = Verdict(True)


def _day(moment: datetime) -> str:
    return moment.astimezone(UTC).date().isoformat()


class AutonomyGovernor:
    """Windowed admission for an agent nobody is watching.

    State lives in the event store so the bounds survive a restart. An agent
    whose daily ceiling resets every time the process bounces has no ceiling.
    """

    def __init__(self, store: Any, *, self_actors: tuple[str, ...] | None = None,
                 source_events_per_minute: int | None = None) -> None:
        self.store = store
        configured = os.getenv("S17_SELF_ACTORS", "")
        self.self_actors = tuple(self_actors if self_actors is not None else
                                 [item.strip() for item in configured.split(",") if item.strip()]
                                 or ["sourcecode", "s17-autonomous"])
        limit = os.getenv("S17_SOURCE_EVENTS_PER_MINUTE", "")
        self.source_events_per_minute = (source_events_per_minute if source_events_per_minute is not None
                                         else int(limit) if limit.strip().isdigit() else 120)

    # ------------------------------------------------------------------ intake

    def admit_event(self, event: EventEnvelope, *, now: datetime | None = None) -> Verdict:
        """Refuse before the event is even matched against subscriptions."""
        moment = now or datetime.now(UTC)

        actor = (event.actor or "").strip()
        if actor and actor in self.self_actors:
            return Verdict(False, f"event was caused by this agent ({actor}); refusing to answer itself",
                           "self_trigger", {"actor": actor})

        if self.source_events_per_minute > 0:
            recent = self.store.count_recent_events(event.source, since=moment - timedelta(minutes=1))
            if recent >= self.source_events_per_minute:
                return Verdict(
                    False,
                    f"source {event.source!r} exceeded {self.source_events_per_minute} events/minute",
                    "source_rate_limit",
                    {"source": event.source, "observed": recent,
                     "limit": self.source_events_per_minute},
                )
        return ADMITTED

    # ------------------------------------------------------------- being awake

    def admit_triage(self, subscription: Subscription, *, now: datetime | None = None) -> Verdict:
        """May we spend a model call deciding whether this event matters?"""
        if subscription.daily_triage_budget is None:
            return ADMITTED
        moment = now or datetime.now(UTC)
        spent = self.store.window_spend(subscription.id, _day(moment), kind="triage")
        if spent >= subscription.daily_triage_budget:
            return Verdict(
                False,
                f"daily triage budget exhausted: ${spent:.8f} of ${subscription.daily_triage_budget:.8f}",
                "daily_triage_budget",
                {"spent_usd": spent, "limit_usd": subscription.daily_triage_budget},
            )
        return ADMITTED

    # ------------------------------------------------------------------- doing

    def admit_run(self, subscription: Subscription, *, now: datetime | None = None) -> Verdict:
        """May a relevant decision actually become a run?

        Admission *claims* the run slot rather than merely reading it. The
        caller awaits the run before recording it, so a check that only reads
        the count is decided on a number that several concurrent deciders all
        see before any of them has run — which is the one case this governor
        exists for, an agent woken by a stream of events.
        """
        moment = now or datetime.now(UTC)
        day = _day(moment)

        # Spend is checked first, so a run refused for money does not burn a
        # slot out of the run ceiling on its way to being refused.
        remaining: float | None = None
        if subscription.daily_budget is not None:
            spent = self.store.window_spend(subscription.id, day, kind="run")
            if spent >= subscription.daily_budget:
                return Verdict(
                    False,
                    f"daily budget exhausted: ${spent:.8f} of ${subscription.daily_budget:.8f}",
                    "daily_budget",
                    {"spent_usd": spent, "limit_usd": subscription.daily_budget},
                )
            remaining = subscription.daily_budget - spent

        reserved, runs = self.store.window_reserve(
            subscription.id, day, kind="run", limit=subscription.max_runs_per_day
        )
        if not reserved:
            return Verdict(
                False,
                f"daily run ceiling reached: {runs} of {subscription.max_runs_per_day}",
                "max_runs_per_day",
                {"runs": runs, "limit": subscription.max_runs_per_day},
            )

        if remaining is not None:
            # Hand the run the smaller of its per-run ceiling and what remains
            # in the window, so one run cannot consume the whole day.
            per_run = subscription.budget if subscription.budget is not None else remaining
            return Verdict(True, "", "", {"effective_budget": min(per_run, remaining)})

        return ADMITTED

    # ----------------------------------------------------------------- ledger

    def record(self, subscription_id: str, *, kind: str, usd: float = 0.0,
               now: datetime | None = None, count: int = 1) -> None:
        """Record what a stage cost. Pass `count=0` when the slot was already
        claimed at admission (runs), so the ceiling is not charged twice."""
        self.store.window_record(subscription_id, _day(now or datetime.now(UTC)),
                                 kind=kind, usd=usd, count=count)

    def snapshot(self, subscription: Subscription, *, now: datetime | None = None) -> dict[str, Any]:
        """What an operator needs to see: how much of each bound is left."""
        day = _day(now or datetime.now(UTC))
        return {
            "subscription_id": subscription.id,
            "window": day,
            "runs": self.store.window_count(subscription.id, day, kind="run"),
            "max_runs_per_day": subscription.max_runs_per_day,
            "run_spend_usd": self.store.window_spend(subscription.id, day, kind="run"),
            "daily_budget_usd": subscription.daily_budget,
            "triage_decisions": self.store.window_count(subscription.id, day, kind="triage"),
            "triage_spend_usd": self.store.window_spend(subscription.id, day, kind="triage"),
            "daily_triage_budget_usd": subscription.daily_triage_budget,
        }
