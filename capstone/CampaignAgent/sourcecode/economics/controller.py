"""The hard controller: the one seam every paid model call passes through.

Two invariants live here, and both are structural rather than aspirational:

1. **No unmetered spend.** :class:`BudgetedGateway` is the only object that holds
   the transport. It charges the run budget from the response's real token counts
   before returning, so a caller cannot obtain a result that was not metered.
2. **No run exceeds its ceiling.** :meth:`BudgetPolicy.decide` is consulted
   *before* the transport is touched. A refusal raises :class:`BudgetRefused`,
   which surfaces as an ordinary failed graph node — visible in the journal, not
   swallowed.

Attribution rides on a :class:`~contextvars.ContextVar`. Each graph node runs in
its own asyncio task, so a context variable set around the worker is naturally
per-node: the controller learns which node and role is spending without every
skill signature growing a parameter.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator, Protocol

from .budget import BudgetRefused, RunBudget
from .policy import BudgetPolicy, Decision
from .pricing import Pricing
from .tiers import TierLadder

#: Key the controller writes its per-node call records under, in a node result.
METER_KEY = "metered_calls"
#: Key the controller writes its per-node budget decisions under.
DECISION_KEY = "budget_decisions"


class ChatTransport(Protocol):
    """What the controller needs from a gateway client: one metered chat call."""

    async def chat(
        self, *, prompt: str, system: str, request: dict[str, Any] | None = None
    ) -> dict[str, Any]: ...


@dataclass
class CallSite:
    """Who is spending: one graph node, for the duration of its worker."""

    node_id: str
    role: str
    tier: str | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)

    def result_fields(self) -> dict[str, Any]:
        """The meter fields to merge into this node's result, hence its journal
        event. The journal is the single durable record; S14 read it as AG-UI
        events, ``sourcecode.telemetry`` reads it as OTel spans."""
        return {METER_KEY: list(self.calls), DECISION_KEY: list(self.decisions)}


_CALL_SITE: ContextVar[CallSite | None] = ContextVar("s17_call_site", default=None)


@contextmanager
def call_site(node_id: str, role: str, tier: str | None = None) -> Iterator[CallSite]:
    """Attribute every call made inside the block to one node."""
    site = CallSite(node_id=node_id, role=role, tier=tier)
    token = _CALL_SITE.set(site)
    try:
        yield site
    finally:
        _CALL_SITE.reset(token)


def current_call_site() -> CallSite | None:
    return _CALL_SITE.get()


class BudgetedGateway:
    """A transport wrapped in the budget policy.

    ``as_text_llm`` hands back the plain ``(prompt, system) -> dict`` callable the
    runtime's skills already expect, so an existing skill becomes budget-aware
    without being touched.
    """

    #: Attribution used when a call is made outside any node's context.
    UNATTRIBUTED = "unattributed"

    def __init__(
        self,
        transport: ChatTransport,
        *,
        budget: RunBudget,
        policy: BudgetPolicy,
        pricing: Pricing,
        ladder: TierLadder,
    ) -> None:
        self.transport = transport
        self.budget, self.policy, self.pricing, self.ladder = budget, policy, pricing, ladder
        self.decisions: list[Decision] = []

    # --- the seam --------------------------------------------------------- #

    def _decide(self, site: CallSite, input_tokens: int | None = None) -> Decision:
        """Decide, then apply a branch by re-basing the node on the run remainder.

        A ``branch`` says: this node's *slice* is too small but the run still has
        room, so re-plan rather than refuse. Applying it is exactly that — drop
        the node's stale allocation and decide again. The label survives into the
        ledger so a burndown can show where the graph branched.
        """
        requested = (
            self.ladder.tier(site.tier) if site.tier else self.ladder.for_role(site.role)
        )
        decide = lambda: self.policy.decide(  # noqa: E731 - one expression, used twice
            node_id=site.node_id, requested_tier=requested, budget=self.budget,
            input_tokens=input_tokens,
        )
        decision = decide()
        if decision.action != "branch":
            return decision
        self.budget.release(site.node_id)
        rebased = decide()
        if rebased.action == "refuse":
            return rebased
        return Decision(
            action="branch",
            node_id=rebased.node_id,
            requested_tier=rebased.requested_tier,
            tier=rebased.tier,
            projected_cost=rebased.projected_cost,
            allowance=rebased.allowance,
            remaining=rebased.remaining,
            pressure=rebased.pressure,
            reason=decision.reason,
            ladder_steps=rebased.ladder_steps,
        )

    async def complete(
        self, prompt: str, system: str, *, request: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Admit, call, meter. There is no path that skips any of the three.

        The prompt is measured before admission, so the projected cost bounds the
        call about to be made rather than an average one. Combined with the tier's
        ``max_tokens`` output ceiling that makes the projection a real upper bound.
        """
        site = current_call_site() or CallSite(self.UNATTRIBUTED, self.UNATTRIBUTED)
        decision = self._decide(site, self.policy.estimate_input_tokens(prompt, system))
        self.decisions.append(decision)
        site.decisions.append(decision.as_dict())

        if not decision.admitted or decision.tier is None:
            detail = self.budget.record_refusal(site.node_id, decision.reason, decision.as_dict())
            raise BudgetRefused(
                f"budget refused a {decision.requested_tier} call for {site.node_id}: {decision.reason}",
                node_id=site.node_id,
                detail=detail,
            )

        body = self.ladder.request_for(decision.tier, overrides=request)
        started = time.time()
        response = await self.transport.chat(prompt=prompt, system=system, request=body)
        latency_ms = (time.time() - started) * 1000.0

        charge = self.budget.charge(
            node_id=site.node_id,
            role=site.role,
            tier=decision.tier.name,
            pricing=self.pricing,
            provider=response.get("provider"),
            model=response.get("model") or decision.tier.model,
            input_tokens=int(response.get("input_tokens") or 0),
            output_tokens=int(response.get("output_tokens") or 0),
            cache_read_tokens=int(response.get("cache_read_input_tokens") or 0),
            cache_write_tokens=int(response.get("cache_creation_input_tokens") or 0),
            projected_cost=decision.projected_cost,
            latency_ms=float(response.get("latency_ms") or latency_ms),
            decision=decision.action,
            requested_tier=decision.requested_tier,
            started_at=started,
        )
        record = {
            **charge.as_dict(),
            "requested_model": decision.tier.request.get("model"),
            "reasoning": decision.tier.request.get("reasoning"),
            "budget_remaining": self.budget.remaining,
            "budget_pressure": self.budget.pressure,
        }
        site.calls.append(record)
        return {
            "text": response.get("text", ""),
            "provider": response.get("provider"),
            "model": response.get("model"),
            "tier": decision.tier.name,
            "cost": charge.cost,
            "input_tokens": charge.input_tokens,
            "output_tokens": charge.output_tokens,
            "budget_decision": decision.action,
        }

    def as_text_llm(self, **request: Any) -> Callable[[str, str], Awaitable[dict[str, Any]]]:
        """The ``(prompt, system)`` callable the carried-forward skills expect."""

        async def llm(prompt: str, system: str) -> dict[str, Any]:
            return await self.complete(prompt, system, request=request or None)

        return llm


class MeteredTransport:
    """Counts transport calls. Wrap the real one to prove nothing bypassed the meter.

    :attr:`calls` counts calls that came back with a response — the ones that must
    each have a charge behind them, so a proof compares it against the length of
    the budget ledger and a gap means a provider call escaped the meter.
    :attr:`failures` counts attempts that raised (a rate limit, a dead provider).
    Those consumed no tokens the gateway could report, so they are deliberately
    not charged, and counting them separately keeps the invariant honest instead
    of quietly widening it.
    """

    def __init__(self, inner: ChatTransport) -> None:
        self.inner = inner
        self.calls = 0
        self.failures = 0
        self.requests: list[dict[str, Any]] = []
        self.errors: list[str] = []

    @property
    def attempts(self) -> int:
        return self.calls + self.failures

    async def chat(
        self, *, prompt: str, system: str, request: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.requests.append(dict(request or {}))
        try:
            response = await self.inner.chat(prompt=prompt, system=system, request=request)
        except Exception as error:
            self.failures += 1
            self.errors.append(f"{type(error).__name__}: {error}")
            raise
        self.calls += 1
        return response
