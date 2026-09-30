"""A run-scoped budget: allowance, spend, reservations, and frontier allocation.

The budget is a ledger, not an opinion. Every admitted call is charged here
before its result is usable, so "no unmetered spend" is a property of the code
path rather than a promise: :meth:`RunBudget.charge` is the only writer, and
:attr:`RunBudget.charges` is the whole audit trail for the run.

Allocation is deliberately simple and inspectable. A slice of the allowance is
held back (``reserve_fraction``) so the terminal node that actually answers is
never starved by its own upstream research, and what remains is split across the
current graph frontier. Re-allocating on every planning round is what makes the
budget follow a live graph whose shape is not known up front.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from .pricing import Pricing


class BudgetRefused(RuntimeError):
    """A call was refused because admitting it would breach the run's ceiling.

    Raised at the call seam, so a refused node fails as a normal graph outcome
    and the planner sees it in the journal. Nothing is silently truncated.
    """

    def __init__(self, message: str, *, node_id: str | None = None, detail: dict[str, Any] | None = None):
        super().__init__(message)
        self.node_id = node_id
        self.detail = detail or {}


@dataclass(frozen=True)
class Charge:
    """One metered provider call."""

    sequence: int
    node_id: str
    role: str
    tier: str
    provider: str | None
    model: str | None
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost: float
    projected_cost: float
    latency_ms: float | None
    started_at: float
    decision: str = "proceed"
    requested_tier: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RunBudget:
    """The allowance one run may spend, and what it has spent so far.

    ``principal`` is the attribution key — tenant, project, user, agent, session,
    whatever string the caller meters against. It is opaque here.
    """

    total: float
    principal: str = "unattributed"
    currency: str = "USD"
    run_id: str | None = None
    reserve_fraction: float = 0.0
    spent: float = 0.0
    reservations: dict[str, float] = field(default_factory=dict)
    charges: list[Charge] = field(default_factory=list)
    refusals: list[dict[str, Any]] = field(default_factory=list)
    calls_by_node: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.total < 0:
            raise ValueError("a budget cannot be negative")
        if not 0.0 <= self.reserve_fraction < 1.0:
            raise ValueError("reserve_fraction must be in [0, 1)")

    # --- state ------------------------------------------------------------ #

    @property
    def remaining(self) -> float:
        """Unspent allowance."""
        return max(0.0, self.total - self.spent)

    @property
    def pressure(self) -> float:
        """Spend ratio in [0, 1]. The single number the policy reads."""
        return 1.0 if self.total <= 0 else min(1.0, self.spent / self.total)

    @property
    def reserve(self) -> float:
        """The slice held back for terminal work."""
        return self.total * self.reserve_fraction

    @property
    def calls(self) -> int:
        return len(self.charges)

    def allowance(self, node_id: str) -> float:
        """What this node may spend: its allocation, or the whole remainder.

        A node with no allocation (one the planner never saw on a frontier, or a
        run with no allocation at all) is bounded by the run remainder alone —
        the run ceiling always holds even when allocation does not.
        """
        allocated = self.reservations.get(node_id)
        if allocated is None:
            return self.remaining
        return max(0.0, min(allocated, self.remaining))

    # --- allocation ------------------------------------------------------- #

    def allocate(self, frontier: Sequence[str], *, reserve_fraction: float | None = None) -> dict[str, float]:
        """Split the spendable remainder evenly across the current frontier.

        Called on every planning round with whatever nodes are now pending, so a
        graph that grows mid-run re-divides rather than overcommitting. Nodes no
        longer on the frontier keep no claim. Returns the new allocation.
        """
        fraction = self.reserve_fraction if reserve_fraction is None else reserve_fraction
        spendable = max(0.0, self.remaining - self.total * fraction)
        unique = list(dict.fromkeys(frontier))
        self.reservations = (
            {node_id: spendable / len(unique) for node_id in unique} if unique else {}
        )
        return dict(self.reservations)

    def release(self, node_id: str) -> None:
        """Drop a node's claim (it finished, failed or was cancelled)."""
        self.reservations.pop(node_id, None)

    # --- the hard controller --------------------------------------------- #

    def can_admit(self, node_id: str, projected_cost: float, *, headroom: float = 0.0) -> bool:
        """Whether a call projected at ``projected_cost`` fits.

        Both bounds must hold: the run remainder (minus headroom) and the node's
        own allowance. This is the check a prompt cannot be trusted to make.
        """
        if projected_cost < 0:
            raise ValueError("projected cost cannot be negative")
        if projected_cost > self.remaining - headroom:
            return False
        return projected_cost <= self.allowance(node_id)

    def record_refusal(self, node_id: str, reason: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
        """Journal a refusal so an exhausted run is auditable, not just failed."""
        entry = {
            "node_id": node_id,
            "reason": reason,
            "spent": self.spent,
            "remaining": self.remaining,
            "pressure": self.pressure,
            **(detail or {}),
        }
        self.refusals.append(entry)
        return entry

    def charge(
        self,
        *,
        node_id: str,
        role: str,
        tier: str,
        pricing: Pricing,
        provider: str | None = None,
        model: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        projected_cost: float = 0.0,
        latency_ms: float | None = None,
        decision: str = "proceed",
        requested_tier: str | None = None,
        started_at: float | None = None,
    ) -> Charge:
        """Meter one completed call. The only place ``spent`` moves."""
        cost = pricing.cost(
            model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
        )
        charge = Charge(
            sequence=len(self.charges) + 1,
            node_id=node_id,
            role=role,
            tier=tier,
            provider=provider,
            model=model,
            input_tokens=int(input_tokens),
            output_tokens=int(output_tokens),
            cache_read_tokens=int(cache_read_tokens),
            cache_write_tokens=int(cache_write_tokens),
            cost=cost,
            projected_cost=projected_cost,
            latency_ms=latency_ms,
            started_at=started_at if started_at is not None else time.time(),
            decision=decision,
            requested_tier=requested_tier,
        )
        self.spent += cost
        self.charges.append(charge)
        self.calls_by_node[node_id] = self.calls_by_node.get(node_id, 0) + 1
        return charge

    def node_calls(self, node_id: str) -> int:
        return self.calls_by_node.get(node_id, 0)

    # --- reporting -------------------------------------------------------- #

    def by_tier(self) -> dict[str, dict[str, float]]:
        rollup: dict[str, dict[str, float]] = {}
        for charge in self.charges:
            row = rollup.setdefault(charge.tier, {"calls": 0, "cost": 0.0, "input_tokens": 0, "output_tokens": 0})
            row["calls"] += 1
            row["cost"] += charge.cost
            row["input_tokens"] += charge.input_tokens
            row["output_tokens"] += charge.output_tokens
        return rollup

    def snapshot(self) -> dict[str, Any]:
        """A JSON-safe view: the number a proof or a burndown widget reads."""
        return {
            "run_id": self.run_id,
            "principal": self.principal,
            "currency": self.currency,
            "total": self.total,
            "spent": self.spent,
            "remaining": self.remaining,
            "pressure": self.pressure,
            "reserve": self.reserve,
            "calls": self.calls,
            "downgrades": sum(1 for c in self.charges if c.decision == "downgrade"),
            "branches": sum(1 for c in self.charges if c.decision == "branch"),
            "refusals": len(self.refusals),
            "reservations": dict(self.reservations),
            "by_tier": self.by_tier(),
            "charges": [c.as_dict() for c in self.charges],
            "refusal_log": list(self.refusals),
        }


def total_cost(charges: Iterable[Charge]) -> float:
    return sum(charge.cost for charge in charges)
