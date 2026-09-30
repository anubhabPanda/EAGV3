"""The budget decision: proceed, downgrade, branch, or refuse.

This is deterministic code and not a prompt, on purpose. TALE (2026) named the
failure: models are *token-elastic*, so a soft "please stay under $X" instruction
leaks — the run sails past the ceiling while sincerely agreeing to it. The only
budget that holds is one a controller enforces before the call is made.

:meth:`BudgetPolicy.decide` is the whole decision surface, and it is pure with
respect to the budget it inspects (it reads state, it does not spend). Four
outcomes, in four numeric regimes:

``proceed``    the requested tier fits the node's allowance.
``downgrade``  pressure has crossed ``downgrade_at``, or the requested tier no
               longer fits, and a cheaper rung does. The graph keeps its shape
               and gets cheaper.
``branch``     no rung fits the node's *allocation*, but the run as a whole still
               has room. The right answer is to re-plan — re-allocate the
               frontier and take the cheapest rung — not to give up.
``refuse``     nothing fits the run remainder, pressure has crossed
               ``refuse_at``, or a call ceiling is hit. The node fails as a
               visible graph outcome; nothing is silently truncated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from ..core.live_graph import Event, GraphPatch, GraphSnapshot, NodeState
from .budget import RunBudget
from .pricing import Pricing
from .tiers import Tier, TierLadder, declare_tiers

Action = Literal["proceed", "downgrade", "branch", "refuse"]


@dataclass(frozen=True)
class PolicyThresholds:
    """Every number the decision reads. All of it comes from ``budgets.yaml``."""

    downgrade_at: float = 0.5
    refuse_at: float = 0.9
    headroom_fraction: float = 0.0
    max_calls_per_run: int = 0
    max_calls_per_node: int = 0
    reserve_fraction: float = 0.0
    chars_per_token: float = 4.0
    input_estimate_safety: float = 1.25

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> PolicyThresholds:
        return cls(
            downgrade_at=float(data.get("downgrade_at", 0.5)),
            refuse_at=float(data.get("refuse_at", 0.9)),
            headroom_fraction=float(data.get("headroom_fraction", 0.0)),
            max_calls_per_run=int(data.get("max_calls_per_run", 0)),
            max_calls_per_node=int(data.get("max_calls_per_node", 0)),
            reserve_fraction=float(data.get("reserve_fraction", 0.0)),
            chars_per_token=float(data.get("chars_per_token", 4.0)),
            input_estimate_safety=float(data.get("input_estimate_safety", 1.25)),
        )


@dataclass(frozen=True)
class Decision:
    """What the controller decided, and every number behind it."""

    action: Action
    node_id: str
    requested_tier: str
    tier: Tier | None
    projected_cost: float
    allowance: float
    remaining: float
    pressure: float
    reason: str
    ladder_steps: int = 0

    @property
    def admitted(self) -> bool:
        return self.action != "refuse"

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "node_id": self.node_id,
            "requested_tier": self.requested_tier,
            "tier": self.tier.name if self.tier else None,
            "model": self.tier.model if self.tier else None,
            "projected_cost": self.projected_cost,
            "allowance": self.allowance,
            "remaining": self.remaining,
            "pressure": self.pressure,
            "ladder_steps": self.ladder_steps,
            "reason": self.reason,
        }


class BudgetPolicy:
    """Turns (requested tier, budget state) into a :class:`Decision`."""

    def __init__(self, ladder: TierLadder, pricing: Pricing, thresholds: PolicyThresholds) -> None:
        self.ladder, self.pricing, self.thresholds = ladder, pricing, thresholds

    # --- estimation ------------------------------------------------------- #

    def estimate_input_tokens(self, *texts: str) -> int:
        """A deliberately pessimistic input-token count for the text being sent.

        Admission has to bound the call it is about to make, and the only input we
        control is the prompt. Characters per token and the safety factor are
        config, because a provider's tokeniser is not ours.
        """
        characters = sum(len(text or "") for text in texts)
        per_token = max(self.thresholds.chars_per_token, 0.1)
        return int(characters / per_token * max(self.thresholds.input_estimate_safety, 1.0)) + 1

    def project(
        self,
        tier: Tier,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> float:
        """The WORST case a call at ``tier`` can cost, priced before it is made.

        Output is bounded by the tier's ``max_tokens``, which the provider honours,
        so the output half of this number is a real ceiling rather than a guess.
        Input defaults to the tier's configured projection and should be replaced
        by an estimate of the actual prompt whenever one exists.
        """
        return self.pricing.cost(
            tier.model,
            input_tokens=tier.projected_input_tokens if input_tokens is None else input_tokens,
            output_tokens=tier.max_output_tokens if output_tokens is None else output_tokens,
        )

    # --- the decision ----------------------------------------------------- #

    def decide(
        self,
        *,
        node_id: str,
        requested_tier: Tier | str | None,
        budget: RunBudget,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> Decision:
        """The one decision function. Pure: it never spends."""
        requested = requested_tier if isinstance(requested_tier, Tier) else self.ladder.tier(requested_tier)
        thresholds = self.thresholds
        headroom = budget.total * thresholds.headroom_fraction
        pressure = budget.pressure
        allowance = budget.allowance(node_id)
        projected = self.project(requested, input_tokens=input_tokens, output_tokens=output_tokens)

        def refusal(reason: str, tier: Tier | None = None, projected_cost: float | None = None) -> Decision:
            return Decision(
                action="refuse", node_id=node_id, requested_tier=requested.name, tier=tier,
                projected_cost=projected if projected_cost is None else projected_cost,
                allowance=allowance, remaining=budget.remaining, pressure=pressure, reason=reason,
            )

        # 1. Call ceilings first: they hold even if every price estimate is wrong,
        #    which is exactly the denial-of-wallet case (a loop, not a big call).
        if thresholds.max_calls_per_run and budget.calls >= thresholds.max_calls_per_run:
            return refusal(f"run call ceiling reached ({budget.calls}/{thresholds.max_calls_per_run})")
        if thresholds.max_calls_per_node and budget.node_calls(node_id) >= thresholds.max_calls_per_node:
            return refusal(
                f"node call ceiling reached ({budget.node_calls(node_id)}/{thresholds.max_calls_per_node})"
            )

        # 2. Exhaustion: at or past the refuse ratio nothing is admitted at any
        #    tier. Cheap is not free, and a run that keeps limping costs money.
        if pressure >= thresholds.refuse_at:
            return refusal(f"spend pressure {pressure:.3f} >= refuse_at {thresholds.refuse_at}")

        # 3. The candidate ladder walk. Under pressure the requested tier is
        #    dropped a rung before it is even priced; then rungs are tried in
        #    descending capability until one fits the node's allowance.
        candidates: list[Tier] = []
        under_pressure = pressure >= thresholds.downgrade_at
        start = self.ladder.downgrade(requested) if under_pressure else requested
        if start is None:
            start = self.ladder.cheapest
        candidates.append(start)
        candidates.extend(self.ladder.cheaper_than(start))

        for tier in candidates:
            cost = self.project(tier, input_tokens=input_tokens, output_tokens=output_tokens)
            if not budget.can_admit(node_id, cost, headroom=headroom):
                continue
            steps = requested.rank - tier.rank
            if steps <= 0:
                return Decision(
                    action="proceed", node_id=node_id, requested_tier=requested.name, tier=tier,
                    projected_cost=cost, allowance=allowance, remaining=budget.remaining,
                    pressure=pressure, reason="requested tier fits the node allowance", ladder_steps=0,
                )
            return Decision(
                action="downgrade", node_id=node_id, requested_tier=requested.name, tier=tier,
                projected_cost=cost, allowance=allowance, remaining=budget.remaining, pressure=pressure,
                reason=(
                    f"pressure {pressure:.3f} >= downgrade_at {thresholds.downgrade_at}"
                    if under_pressure
                    else f"{requested.name} does not fit the {allowance:.6f} node allowance"
                ),
                ladder_steps=steps,
            )

        # 4. No rung fits this node's ALLOCATION. If the run itself still has room
        #    the honest move is to re-plan: re-allocate the frontier and take the
        #    cheapest rung. That is a branch, not a refusal.
        cheapest = self.ladder.cheapest
        cheapest_cost = self.project(cheapest, input_tokens=input_tokens, output_tokens=output_tokens)
        if cheapest_cost <= budget.remaining - headroom:
            return Decision(
                action="branch", node_id=node_id, requested_tier=requested.name, tier=cheapest,
                projected_cost=cheapest_cost, allowance=allowance, remaining=budget.remaining,
                pressure=pressure,
                reason=(
                    f"no tier fits the {allowance:.6f} node allocation, but the run still holds "
                    f"{budget.remaining:.6f}: re-allocate the frontier and take {cheapest.name}"
                ),
                ladder_steps=requested.rank - cheapest.rank,
            )

        return refusal(
            f"cheapest tier {cheapest.name} projects {cheapest_cost:.6f}, run holds "
            f"{budget.remaining:.6f} (headroom {headroom:.6f})",
            tier=None,
            projected_cost=cheapest_cost,
        )


@dataclass
class BudgetAwarePlanner:
    """Wraps any planner so the graph plans against a ceiling.

    Two additive things happen around the inner planner, and neither changes graph
    semantics: every new node is stamped with the capability tier its role
    declares, and the run budget is re-allocated across the frontier the patch
    produces. Allocation therefore follows a graph whose shape is discovered as
    it runs, which is the whole point of a live graph.
    """

    inner: Any
    ladder: TierLadder
    budget: RunBudget
    reserve_fraction: float = 0.0
    allocations: list[dict[str, Any]] = field(default_factory=list)

    @property
    def last_selection(self) -> dict[str, Any]:
        """Pass the inner planner's own trace through unchanged."""
        return getattr(self.inner, "last_selection", {"mode": "deterministic"})

    async def plan(self, graph: GraphSnapshot, event: Event) -> GraphPatch:
        patch = declare_tiers(await self.inner.plan(graph, event), self.ladder)
        frontier = self._frontier(graph, patch)
        allocation = self.budget.allocate(frontier, reserve_fraction=self.reserve_fraction)
        self.allocations.append(
            {
                "trigger_event": event.sequence,
                "frontier": list(frontier),
                "per_node": allocation,
                "remaining": self.budget.remaining,
                "tiers": {task.id: task.metadata.get("tier") for task in patch.add},
            }
        )
        return patch

    def _frontier(self, graph: GraphSnapshot, patch: GraphPatch) -> tuple[str, ...]:
        """Nodes that may still spend: pending/waiting/running plus the new ones."""
        if patch.finish:
            return ()
        live = {NodeState.PENDING, NodeState.WAITING, NodeState.RUNNING}
        cancelled = set(patch.cancel)
        existing = [
            node_id
            for node_id, node in graph.nodes.items()
            if node["state"] in live and node_id not in cancelled
        ]
        added = [task.id for task in patch.add]
        return tuple(dict.fromkeys([*existing, *added]))
