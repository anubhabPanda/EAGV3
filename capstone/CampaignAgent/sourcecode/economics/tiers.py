"""Capability tiers: what a node declares, and what the gateway is asked for.

A node does not pick a model. It declares the *tier* it needs, and the tier is a
config name — ``tiers.yaml`` maps it to the gateway request fields (provider,
model, reasoning effort, token ceiling). Nothing here knows any provider or
model name, so repointing a tier is a config edit.

``TierLadder`` also owns what "downgrade" means: the ladder is the configured
``order``, cheapest first, and downgrading is one step towards its head.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core.live_graph import GraphPatch, TaskSpec

#: Node metadata key a task uses to declare its tier.
TIER_KEY = "tier"


@dataclass(frozen=True)
class Tier:
    """One rung of the ladder."""

    name: str
    rank: int
    request: dict[str, Any] = field(default_factory=dict)
    price_model: str | None = None
    projected_input_tokens: int = 0
    projected_output_tokens: int = 0

    @property
    def model(self) -> str | None:
        """The model this tier is billed against."""
        return self.price_model or self.request.get("model")

    @property
    def max_output_tokens(self) -> int:
        """The HARD output bound for this tier.

        ``max_tokens`` is the number the provider honours, so it — not a guess —
        is what admission prices. A tier with no ceiling falls back to its
        configured projection, which is then only an estimate.
        """
        ceiling = self.request.get("max_tokens")
        return int(ceiling) if ceiling else self.projected_output_tokens


class TierLadder:
    """The configured tiers, ordered cheapest first, plus the role mapping."""

    def __init__(
        self,
        tiers: dict[str, Tier],
        order: tuple[str, ...],
        role_tiers: dict[str, str],
        default_tier: str,
    ) -> None:
        if not order:
            raise ValueError("a tier ladder needs at least one tier in `order`")
        missing = [name for name in order if name not in tiers]
        if missing:
            raise ValueError(f"tiers.yaml order names undefined tiers: {missing}")
        if default_tier not in tiers:
            raise ValueError(f"tiers.yaml default_tier {default_tier!r} is not a defined tier")
        self._tiers, self._order = tiers, tuple(order)
        self._role_tiers = dict(role_tiers)
        self._default = default_tier

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> TierLadder:
        raw = data.get("tiers") or {}
        order = tuple(str(name) for name in (data.get("order") or sorted(raw)))
        tiers = {}
        for rank, name in enumerate(order):
            row = raw.get(name) or {}
            tiers[name] = Tier(
                name=name,
                rank=rank,
                request=dict(row.get("request") or {}),
                price_model=row.get("price_model") or (row.get("request") or {}).get("model"),
                projected_input_tokens=int(row.get("projected_input_tokens", 0)),
                projected_output_tokens=int(row.get("projected_output_tokens", 0)),
            )
        role_tiers = {str(k): str(v) for k, v in (data.get("role_tiers") or {}).items()}
        default = str(data.get("default_tier") or role_tiers.get("default") or order[0])
        return cls(tiers, order, role_tiers, default)

    # --- lookup ----------------------------------------------------------- #

    @property
    def names(self) -> tuple[str, ...]:
        """Tier names, cheapest first."""
        return self._order

    @property
    def cheapest(self) -> Tier:
        return self._tiers[self._order[0]]

    @property
    def most_capable(self) -> Tier:
        return self._tiers[self._order[-1]]

    @property
    def default(self) -> Tier:
        return self._tiers[self._default]

    def tier(self, name: str | None) -> Tier:
        """The named tier, or the configured default when unknown/absent."""
        if name and name in self._tiers:
            return self._tiers[name]
        return self.default

    def for_role(self, role: str | None) -> Tier:
        """The tier a graph role declares it needs, from ``role_tiers``."""
        if role and role in self._role_tiers:
            return self.tier(self._role_tiers[role])
        if "default" in self._role_tiers:
            return self.tier(self._role_tiers["default"])
        return self.default

    def downgrade(self, tier: Tier) -> Tier | None:
        """One rung cheaper, or ``None`` at the bottom of the ladder."""
        return self._tiers[self._order[tier.rank - 1]] if tier.rank > 0 else None

    def cheaper_than(self, tier: Tier) -> tuple[Tier, ...]:
        """Every rung below ``tier``, most capable of those first."""
        return tuple(self._tiers[name] for name in reversed(self._order[: tier.rank]))

    def request_for(self, tier: Tier, *, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        """The gateway request body fields for this tier, plus caller overrides."""
        return {**tier.request, **(overrides or {})}


def declare_tiers(patch: GraphPatch, ladder: TierLadder) -> GraphPatch:
    """Stamp each newly added task with the tier its role declares.

    Pure and additive: a task that already declares a tier keeps it, so a planner
    (or a test) can ask for a specific rung. Everything else inherits the tier
    its role maps to in ``tiers.yaml``.
    """
    if not patch.add:
        return patch
    annotated: list[TaskSpec] = []
    for task in patch.add:
        if task.metadata.get(TIER_KEY):
            annotated.append(task)
            continue
        role = task.metadata.get("agent") or task.skill
        tier = ladder.for_role(role)
        annotated.append(
            TaskSpec(task.id, task.skill, task.input, {**task.metadata, TIER_KEY: tier.name})
        )
    return GraphPatch(
        add=tuple(annotated),
        connect=patch.connect,
        cancel=patch.cancel,
        wait=patch.wait,
        resume=patch.resume,
        finish=patch.finish,
        reason=patch.reason,
        metadata=patch.metadata,
    )
