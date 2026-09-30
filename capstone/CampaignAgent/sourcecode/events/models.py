from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class EventEnvelope(BaseModel):
    """One normalized fact from cron, a webhook, Pub/Sub, or another agent."""

    id: str = Field(min_length=1, max_length=500)
    source: str = Field(min_length=1, max_length=500)
    type: str = Field(min_length=1, max_length=500)
    subject: str | None = Field(default=None, max_length=2_000)
    occurred_at: datetime
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    data: dict[str, Any] = Field(default_factory=dict)
    traceparent: str | None = Field(default=None, max_length=500)
    # Who caused this fact. An agent that acts in a system it also watches will
    # see its own actions come back as events; without an actor it cannot tell
    # them apart from anybody else's, and one reply to a watched mailbox becomes
    # a loop that only a spend ceiling stops, after the fact.
    actor: str | None = Field(default=None, max_length=500)


class Subscription(BaseModel):
    """Authority and intent configured by a human, separate from event data."""

    id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.-]+$")
    instruction: str = Field(min_length=1, max_length=20_000)
    event_types: list[str] = Field(default_factory=lambda: ["*"], min_length=1, max_length=50)
    sources: list[str] = Field(default_factory=lambda: ["*"], min_length=1, max_length=50)
    tenant_id: str = Field(min_length=1, max_length=200)
    project_id: str | None = Field(default=None, max_length=200)
    user_id: str | None = Field(default=None, max_length=200)
    agent_id: str | None = Field(default="s17-autonomous", max_length=200)
    allowed_side_effects: list[str] = Field(default_factory=list, max_length=50)
    # Per-run ceiling, inherited from Session 15's hard controller.
    budget: float | None = Field(default=None, gt=0)
    # Per-window ceilings. A per-run ceiling does not bound an agent that starts
    # its own runs: it simply starts more of them. These bound the window.
    daily_budget: float | None = Field(default=None, gt=0)
    max_runs_per_day: int | None = Field(default=None, gt=0)
    # Triage costs money on every matching event, whether or not work follows.
    # This is the ceiling on being awake, as distinct from the ceiling on doing.
    daily_triage_budget: float | None = Field(default=None, gt=0)
    # Actors whose events this subscription refuses, so the agent does not
    # answer itself. The runtime's own identity is always included.
    ignore_actors: list[str] = Field(default_factory=list, max_length=50)
    enabled: bool = True

