"""Budget-aware planning: the agent becomes economically self-aware.

A run is created with a ceiling and a principal. The planner declares the
capability tier each node needs and re-allocates the ceiling across the live
frontier; the controller admits, meters and — under pressure — downgrades,
branches or refuses. Every threshold, tier, price and allowance is config.

Two things stay true no matter what the model does with its tokens: no call is
made without being metered, and no run spends past its ceiling. Both are
enforced in code, because a budget asked for in a prompt leaks.
"""

from .budget import BudgetRefused, Charge, RunBudget, total_cost
from .config import EconomicsConfig, config_dir
from .controller import (
    DECISION_KEY,
    METER_KEY,
    BudgetedGateway,
    CallSite,
    ChatTransport,
    MeteredTransport,
    call_site,
    current_call_site,
)
from .policy import Action, BudgetAwarePlanner, BudgetPolicy, Decision, PolicyThresholds
from .pricing import ModelPrice, Pricing
from .tiers import TIER_KEY, Tier, TierLadder, declare_tiers

__all__ = [
    "Action",
    "BudgetAwarePlanner",
    "BudgetPolicy",
    "BudgetRefused",
    "BudgetedGateway",
    "CallSite",
    "Charge",
    "ChatTransport",
    "DECISION_KEY",
    "Decision",
    "EconomicsConfig",
    "METER_KEY",
    "MeteredTransport",
    "ModelPrice",
    "PolicyThresholds",
    "Pricing",
    "RunBudget",
    "TIER_KEY",
    "Tier",
    "TierLadder",
    "call_site",
    "config_dir",
    "current_call_site",
    "declare_tiers",
    "total_cost",
]
