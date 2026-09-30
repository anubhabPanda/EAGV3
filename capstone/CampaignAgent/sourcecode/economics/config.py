"""Load the economics configuration. Config decides; Python only enforces.

Three files, all outside the package:

``tiers.yaml``    the capability ladder and the role -> tier mapping
``pricing.yaml``  per-model prices
``budgets.yaml``  allowances and every policy threshold

Adding a model, a tier, a role or a budget must never require a Python edit, so
nothing in ``sourcecode`` names a provider, a model, a price or a threshold. The
directory is resolved from ``S17_CONFIG_DIR`` when set, else ``config/`` beside
the package, so a deployment can point at its own copy.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .budget import RunBudget
from .policy import BudgetPolicy, PolicyThresholds
from .pricing import Pricing
from .tiers import TierLadder

#: ``config/`` as shipped next to the package.
DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"

TIERS_FILE = "tiers.yaml"
PRICING_FILE = "pricing.yaml"
BUDGETS_FILE = "budgets.yaml"


def config_dir(explicit: str | Path | None = None) -> Path:
    """Where the config lives: the argument, then ``S17_CONFIG_DIR``, then default."""
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    from_env = os.getenv("S17_CONFIG_DIR")
    if from_env:
        return Path(from_env).expanduser().resolve()
    return DEFAULT_CONFIG_DIR


def _read(directory: Path, name: str) -> dict[str, Any]:
    path = directory / name
    if not path.exists():
        raise FileNotFoundError(f"economics config {name} not found in {directory}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping")
    return data


@dataclass(frozen=True)
class EconomicsConfig:
    """The loaded ladder, price table and thresholds, plus where they came from."""

    ladder: TierLadder
    pricing: Pricing
    thresholds: PolicyThresholds
    default_budget: float
    principal_limits: dict[str, float] = field(default_factory=dict)
    directory: Path = DEFAULT_CONFIG_DIR

    @classmethod
    def load(cls, directory: str | Path | None = None) -> EconomicsConfig:
        resolved = config_dir(directory)
        tiers_data = _read(resolved, TIERS_FILE)
        pricing_data = _read(resolved, PRICING_FILE)
        budget_data = _read(resolved, BUDGETS_FILE)
        return cls(
            ladder=TierLadder.from_mapping(tiers_data),
            pricing=Pricing.from_mapping(pricing_data),
            thresholds=PolicyThresholds.from_mapping(budget_data),
            default_budget=float(budget_data.get("default_budget", 0.0)),
            principal_limits={
                str(name): float(limit) for name, limit in (budget_data.get("principals") or {}).items()
            },
            directory=resolved,
        )

    def policy(self) -> BudgetPolicy:
        return BudgetPolicy(self.ladder, self.pricing, self.thresholds)

    def ceiling_for(self, principal: str, requested: float | None = None) -> float:
        """The allowance a principal actually gets.

        A configured per-principal limit always wins when it is the smaller
        number: a caller may ask for less than its cap, never for more.
        """
        amount = self.default_budget if requested is None else float(requested)
        limit = self.principal_limits.get(principal)
        return min(amount, limit) if limit is not None else amount

    def budget(
        self,
        *,
        principal: str = "unattributed",
        amount: float | None = None,
        run_id: str | None = None,
    ) -> RunBudget:
        """A run budget honouring the configured ceiling and reserve."""
        return RunBudget(
            total=self.ceiling_for(principal, amount),
            principal=principal,
            currency=self.pricing.currency,
            run_id=run_id,
            reserve_fraction=self.thresholds.reserve_fraction,
        )

    def describe(self) -> dict[str, Any]:
        """What a proof writes into its JSON so the run is reproducible."""
        return {
            "directory": str(self.directory),
            "currency": self.pricing.currency,
            "tier_order": list(self.ladder.names),
            "default_tier": self.ladder.default.name,
            "tier_models": {name: self.ladder.tier(name).model for name in self.ladder.names},
            "default_budget": self.default_budget,
            "thresholds": {
                "downgrade_at": self.thresholds.downgrade_at,
                "refuse_at": self.thresholds.refuse_at,
                "headroom_fraction": self.thresholds.headroom_fraction,
                "reserve_fraction": self.thresholds.reserve_fraction,
                "max_calls_per_run": self.thresholds.max_calls_per_run,
                "max_calls_per_node": self.thresholds.max_calls_per_node,
            },
        }
