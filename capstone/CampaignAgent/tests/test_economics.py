"""The economics layer: pricing, tiers, allocation, and the four decisions.

Hermetic. The ladder and thresholds are built in the test rather than read from
``config/``, which is the point: nothing in the library knows a tier name, a
model, a price or a threshold, so a test can invent its own and the same code
path runs. No network, no gateway, no provider key.
"""

from __future__ import annotations

import pytest

from sourcecode.core.live_graph import GraphPatch, TaskSpec
from sourcecode.economics import (
    TIER_KEY,
    BudgetedGateway,
    BudgetPolicy,
    BudgetRefused,
    EconomicsConfig,
    MeteredTransport,
    PolicyThresholds,
    Pricing,
    RunBudget,
    TierLadder,
    call_site,
    declare_tiers,
)

# A ladder with three deliberately arbitrary names, so the test proves the code
# never depends on the names shipped in config/.
LADDER_DATA = {
    "order": ["thrifty", "middling", "lavish"],
    "default_tier": "middling",
    "tiers": {
        "thrifty": {"request": {"provider": "p", "model": "cheap-1", "max_tokens": 100},
                    "projected_input_tokens": 1000, "projected_output_tokens": 100},
        "middling": {"request": {"provider": "p", "model": "mid-1", "max_tokens": 400},
                     "projected_input_tokens": 1000, "projected_output_tokens": 400},
        "lavish": {"request": {"provider": "p", "model": "dear-1", "max_tokens": 2000},
                   "projected_input_tokens": 1000, "projected_output_tokens": 2000},
    },
    "role_tiers": {"default": "middling", "scout": "thrifty", "closer": "lavish"},
}

PRICING_DATA = {
    "currency": "USD",
    "unit_tokens": 1_000_000,
    "default": {"input": 100.0, "output": 100.0},
    "models": {
        "cheap-1": {"input": 1.0, "output": 1.0},
        "mid-1": {"input": 1.0, "output": 1.0},
        "dear-1": {"input": 1.0, "output": 1.0},
    },
    "cache_read_multiplier": 0.1,
}


@pytest.fixture
def ladder() -> TierLadder:
    return TierLadder.from_mapping(LADDER_DATA)


@pytest.fixture
def pricing() -> Pricing:
    return Pricing.from_mapping(PRICING_DATA)


# --------------------------------------------------------------------------- #
# pricing.py
# --------------------------------------------------------------------------- #

def test_price_comes_from_config_not_code(pricing):
    # 1000 input + 400 output at $1/MTok each.
    assert pricing.cost("mid-1", input_tokens=1000, output_tokens=400) == pytest.approx(1400 / 1e6)


def test_unknown_model_falls_back_to_the_default_row_not_to_free(pricing):
    assert pricing.cost("never-heard-of-it", input_tokens=1000) > 0
    assert not pricing.is_priced("never-heard-of-it")
    assert pricing.is_priced("mid-1")


def test_a_decorated_model_id_still_prices_via_longest_prefix(pricing):
    assert pricing.cost("mid-1-002", input_tokens=1000) == pricing.cost("mid-1", input_tokens=1000)


def test_cache_reads_are_billed_at_the_configured_multiplier(pricing):
    fresh = pricing.cost("mid-1", input_tokens=1000)
    cached = pricing.cost("mid-1", cache_read_tokens=1000)
    assert cached == pytest.approx(fresh * 0.1)


# --------------------------------------------------------------------------- #
# tiers.py
# --------------------------------------------------------------------------- #

def test_ladder_is_ordered_cheapest_first_and_downgrade_walks_it(ladder):
    assert ladder.names == ("thrifty", "middling", "lavish")
    assert ladder.cheapest.name == "thrifty"
    assert ladder.most_capable.name == "lavish"
    assert ladder.downgrade(ladder.tier("lavish")).name == "middling"
    assert ladder.downgrade(ladder.tier("middling")).name == "thrifty"
    assert ladder.downgrade(ladder.tier("thrifty")) is None


def test_a_role_declares_its_tier_from_config(ladder):
    assert ladder.for_role("scout").name == "thrifty"
    assert ladder.for_role("closer").name == "lavish"
    # An unlisted role gets the configured default, never a guess.
    assert ladder.for_role("some_role_nobody_configured").name == "middling"


def test_tier_expands_to_gateway_request_fields(ladder):
    body = ladder.request_for(ladder.tier("thrifty"), overrides={"max_tokens": 4000})
    assert body["provider"] == "p" and body["model"] == "cheap-1"
    assert body["max_tokens"] == 4000  # a caller override wins


def test_declare_tiers_stamps_new_nodes_and_respects_an_explicit_one(ladder):
    patch = GraphPatch(add=(
        TaskSpec("a", "scout"),
        TaskSpec("b", "closer", {}, {"agent": "closer"}),
        TaskSpec("c", "scout", {}, {TIER_KEY: "lavish"}),
    ))
    declared = declare_tiers(patch, ladder)
    tiers = {task.id: task.metadata[TIER_KEY] for task in declared.add}
    assert tiers == {"a": "thrifty", "b": "lavish", "c": "lavish"}


def test_declare_tiers_leaves_everything_else_alone(ladder):
    patch = GraphPatch(add=(TaskSpec("a", "scout"),), connect=(("a", "b"),), cancel=("z",),
                       finish=True, reason="why")
    declared = declare_tiers(patch, ladder)
    assert declared.connect == patch.connect
    assert declared.cancel == patch.cancel
    assert declared.finish is True and declared.reason == "why"


# --------------------------------------------------------------------------- #
# budget.py
# --------------------------------------------------------------------------- #

def test_allocation_splits_the_remainder_after_the_reserve():
    budget = RunBudget(total=1.0, reserve_fraction=0.2)
    allocation = budget.allocate(["a", "b", "c", "d"])
    assert sum(allocation.values()) == pytest.approx(0.8)
    assert allocation["a"] == pytest.approx(0.2)


def test_reallocation_follows_a_graph_that_grows_mid_run():
    budget = RunBudget(total=1.0, reserve_fraction=0.0)
    budget.allocate(["a", "b"])
    assert budget.allowance("a") == pytest.approx(0.5)
    budget.allocate(["a", "b", "c", "d"])  # the planner discovered two more nodes
    assert budget.allowance("a") == pytest.approx(0.25)


def test_a_node_never_on_a_frontier_is_still_bounded_by_the_run(pricing):
    budget = RunBudget(total=0.001)
    assert budget.allowance("never-allocated") == pytest.approx(0.001)
    assert not budget.can_admit("never-allocated", 0.002)


def test_charge_is_the_only_thing_that_moves_spent(ladder, pricing):
    budget = RunBudget(total=1.0)
    budget.charge(node_id="a", role="scout", tier="thrifty", pricing=pricing,
                  model="cheap-1", input_tokens=1000, output_tokens=1000)
    assert budget.spent == pytest.approx(2000 / 1e6)
    assert budget.calls == 1 and budget.node_calls("a") == 1
    assert budget.snapshot()["charges"][0]["model"] == "cheap-1"


# --------------------------------------------------------------------------- #
# policy.py — the decision function
# --------------------------------------------------------------------------- #

def policy(ladder, pricing, **overrides) -> BudgetPolicy:
    defaults = dict(downgrade_at=0.5, refuse_at=0.9, headroom_fraction=0.0,
                    max_calls_per_run=0, max_calls_per_node=0)
    return BudgetPolicy(ladder, pricing, PolicyThresholds(**{**defaults, **overrides}))


def test_proceeds_at_the_requested_tier_when_there_is_room(ladder, pricing):
    budget = RunBudget(total=1.0)
    decision = policy(ladder, pricing).decide(node_id="a", requested_tier="lavish", budget=budget)
    assert decision.action == "proceed"
    assert decision.tier.name == "lavish"
    assert decision.ladder_steps == 0


def test_downgrades_one_rung_once_pressure_crosses_the_threshold(ladder, pricing):
    budget = RunBudget(total=1.0, spent=0.6)  # pressure 0.6 >= downgrade_at 0.5
    decision = policy(ladder, pricing).decide(node_id="a", requested_tier="lavish", budget=budget)
    assert decision.action == "downgrade"
    assert decision.tier.name == "middling"
    assert decision.ladder_steps == 1
    assert "downgrade_at" in decision.reason


def test_downgrades_when_the_node_allowance_cannot_cover_the_requested_tier(ladder, pricing):
    budget = RunBudget(total=1.0)
    # lavish projects 3000 tokens -> 0.003; give the node less than that but more
    # than middling's 0.0014.
    budget.reservations = {"a": 0.0020}
    decision = policy(ladder, pricing).decide(node_id="a", requested_tier="lavish", budget=budget)
    assert decision.action == "downgrade"
    assert decision.tier.name == "middling"
    assert "node allowance" in decision.reason


def test_branches_when_the_slice_is_too_small_but_the_run_still_holds_money(ladder, pricing):
    budget = RunBudget(total=1.0)
    budget.reservations = {"a": 0.0000001}  # no rung fits this slice
    decision = policy(ladder, pricing).decide(node_id="a", requested_tier="lavish", budget=budget)
    assert decision.action == "branch"
    assert decision.tier.name == "thrifty"
    assert "re-allocate" in decision.reason


def test_refuses_at_exhaustion_regardless_of_tier(ladder, pricing):
    budget = RunBudget(total=1.0, spent=0.95)  # pressure 0.95 >= refuse_at 0.9
    for tier in ladder.names:
        decision = policy(ladder, pricing).decide(node_id="a", requested_tier=tier, budget=budget)
        assert decision.action == "refuse"
        assert not decision.admitted


def test_refuses_when_even_the_cheapest_tier_does_not_fit_the_remainder(ladder, pricing):
    budget = RunBudget(total=0.0000001)
    decision = policy(ladder, pricing).decide(node_id="a", requested_tier="thrifty", budget=budget)
    assert decision.action == "refuse"
    assert "cheapest tier" in decision.reason


def test_call_ceilings_refuse_even_when_the_money_is_untouched(ladder, pricing):
    budget = RunBudget(total=1_000_000.0)
    budget.charges = [None] * 5  # type: ignore[list-item]
    decision = policy(ladder, pricing, max_calls_per_run=5).decide(
        node_id="a", requested_tier="thrifty", budget=budget)
    assert decision.action == "refuse" and "run call ceiling" in decision.reason

    node_budget = RunBudget(total=1_000_000.0)
    node_budget.calls_by_node = {"a": 3}
    node_decision = policy(ladder, pricing, max_calls_per_node=3).decide(
        node_id="a", requested_tier="thrifty", budget=node_budget)
    assert node_decision.action == "refuse" and "node call ceiling" in node_decision.reason


def test_the_decision_is_pure_it_never_spends(ladder, pricing):
    budget = RunBudget(total=1.0)
    before = budget.spent
    for _ in range(5):
        policy(ladder, pricing).decide(node_id="a", requested_tier="lavish", budget=budget)
    assert budget.spent == before and budget.calls == 0


# --------------------------------------------------------------------------- #
# controller.py — the hard controller at the call seam
# --------------------------------------------------------------------------- #

class FakeTransport:
    """A gateway stand-in that reports usage the way the real one does."""

    def __init__(self, *, input_tokens=1000, output_tokens=400, model="mid-1"):
        self.input_tokens, self.output_tokens, self.model = input_tokens, output_tokens, model
        self.seen: list[dict] = []

    async def chat(self, *, prompt, system, request=None):
        self.seen.append(dict(request or {}))
        return {"text": "ok", "provider": "p_1", "model": (request or {}).get("model", self.model),
                "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0, "latency_ms": 5}


def controller(ladder, pricing, budget, **overrides) -> tuple[BudgetedGateway, MeteredTransport]:
    transport = MeteredTransport(FakeTransport())
    return (
        BudgetedGateway(transport, budget=budget, policy=policy(ladder, pricing, **overrides),
                        pricing=pricing, ladder=ladder),
        transport,
    )


async def test_every_admitted_call_is_metered_none_bypasses(ladder, pricing):
    budget = RunBudget(total=1.0)
    gateway, transport = controller(ladder, pricing, budget)
    for index in range(4):
        with call_site(f"node_{index}", "scout"):
            await gateway.complete("p", "s")
    # The invariant: transport calls and ledger entries agree exactly.
    assert transport.calls == budget.calls == 4
    assert budget.spent == pytest.approx(4 * 1400 / 1e6)


async def test_the_tier_reaches_the_gateway_as_request_fields(ladder, pricing):
    budget = RunBudget(total=1.0)
    gateway, transport = controller(ladder, pricing, budget)
    with call_site("a", "scout"):
        await gateway.complete("p", "s")
    assert transport.requests[0]["model"] == "cheap-1"
    assert transport.requests[0]["max_tokens"] == 100


async def test_a_refusal_raises_and_never_reaches_the_transport(ladder, pricing):
    budget = RunBudget(total=0.0000001)
    gateway, transport = controller(ladder, pricing, budget)
    with call_site("a", "scout"):
        with pytest.raises(BudgetRefused):
            await gateway.complete("p", "s")
    assert transport.calls == 0
    assert budget.spent == 0.0
    assert len(budget.refusals) == 1


async def test_the_run_ceiling_holds_across_a_long_sequence_of_calls(ladder, pricing):
    """The headline invariant: spend never crosses the ceiling, whatever is asked."""
    budget = RunBudget(total=0.01)
    gateway, transport = controller(ladder, pricing, budget)
    refusals = 0
    for index in range(500):
        with call_site(f"node_{index % 7}", "closer"):
            try:
                await gateway.complete("p", "s")
            except BudgetRefused:
                refusals += 1
    assert budget.spent <= budget.total
    assert refusals > 0
    assert transport.calls == budget.calls


async def test_pressure_produces_a_downgrade_that_the_gateway_actually_applies(ladder, pricing):
    budget = RunBudget(total=1.0, spent=0.6)
    gateway, transport = controller(ladder, pricing, budget)
    with call_site("a", "closer"):  # closer asks for the top rung
        result = await gateway.complete("p", "s")
    assert result["budget_decision"] == "downgrade"
    assert result["tier"] == "middling"
    assert transport.requests[0]["model"] == "mid-1"


async def test_a_branch_rebases_the_node_and_still_meters_the_call(ladder, pricing):
    budget = RunBudget(total=1.0)
    budget.reservations = {"a": 0.0000001}
    gateway, transport = controller(ladder, pricing, budget)
    with call_site("a", "closer"):
        result = await gateway.complete("p", "s")
    assert result["budget_decision"] == "branch"
    assert transport.calls == 1 and budget.calls == 1
    assert budget.snapshot()["branches"] == 1


async def test_admission_prices_the_prompt_it_is_about_to_send(ladder, pricing):
    """The projection bounds THIS call, not an average one."""
    budget = RunBudget(total=1.0)
    gateway, _ = controller(ladder, pricing, budget)
    short = gateway.policy.estimate_input_tokens("hi", "")
    long = gateway.policy.estimate_input_tokens("x" * 40_000, "")
    assert long > short
    # ...and it over-estimates on purpose: 40k characters is ~10k tokens at four
    # characters each, and the safety factor pushes the admitted figure above it.
    assert long > 40_000 / 4


async def test_a_transport_that_ignores_max_tokens_still_gets_halted(ladder, pricing):
    """The honest limit of a projection, and the backstop that survives it.

    Admission bounds output with the tier's ``max_tokens``. A provider that
    returns far more than it was asked for breaks that bound — so the run can
    overshoot on the call already in flight. What must still hold is that it stops
    immediately afterwards, so the overshoot is one call and not a runaway.
    """

    class LyingTransport:
        async def chat(self, *, prompt, system, request=None):
            return {"text": "x", "provider": "p_1", "model": "mid-1",
                    "input_tokens": 1000, "output_tokens": 200_000,
                    "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0, "latency_ms": 1}

    budget = RunBudget(total=0.01)
    transport = MeteredTransport(LyingTransport())
    gateway = BudgetedGateway(transport, budget=budget, policy=policy(ladder, pricing),
                              pricing=pricing, ladder=ladder)
    refusals = 0
    for index in range(50):
        with call_site(f"n{index}", "scout"):
            try:
                await gateway.complete("p", "s")
            except BudgetRefused:
                refusals += 1
    assert budget.calls == 1, "spend must stop the moment the ledger says it is over"
    assert refusals == 49
    assert transport.calls == budget.calls


async def test_the_node_result_carries_the_meter_into_the_journal(ladder, pricing):
    budget = RunBudget(total=1.0)
    gateway, _ = controller(ladder, pricing, budget)
    with call_site("a", "scout") as site:
        await gateway.complete("p", "s")
        await gateway.complete("p", "s")
    fields = site.result_fields()
    assert len(fields["metered_calls"]) == 2
    assert len(fields["budget_decisions"]) == 2
    assert fields["metered_calls"][0]["cost"] > 0


# --------------------------------------------------------------------------- #
# config.py
# --------------------------------------------------------------------------- #

def test_the_shipped_config_loads_and_describes_itself():
    config = EconomicsConfig.load()
    described = config.describe()
    assert described["tier_order"]
    assert described["default_budget"] > 0
    assert set(described["thresholds"]) >= {"downgrade_at", "refuse_at", "reserve_fraction"}


def test_the_shipped_ladder_really_gets_cheaper_going_down():
    config = EconomicsConfig.load()
    projected = [config.policy().project(config.ladder.tier(name)) for name in config.ladder.names]
    assert projected == sorted(projected), projected
    assert projected[-1] > projected[0]


def test_a_principal_limit_caps_what_a_caller_may_ask_for(tmp_path):
    (tmp_path / "tiers.yaml").write_text(_yaml(LADDER_DATA))
    (tmp_path / "pricing.yaml").write_text(_yaml(PRICING_DATA))
    (tmp_path / "budgets.yaml").write_text(_yaml({
        "default_budget": 0.5, "reserve_fraction": 0.1, "downgrade_at": 0.5, "refuse_at": 0.9,
        "principals": {"tenant/capped": 0.01},
    }))
    config = EconomicsConfig.load(tmp_path)
    assert config.ceiling_for("tenant/capped", 10.0) == 0.01
    assert config.ceiling_for("tenant/uncapped", 10.0) == 10.0
    assert config.ceiling_for("tenant/uncapped") == 0.5  # the file's default
    assert config.budget(principal="tenant/capped", amount=10.0).total == 0.01


def test_a_missing_config_file_is_a_loud_failure(tmp_path):
    with pytest.raises(FileNotFoundError):
        EconomicsConfig.load(tmp_path)


def _yaml(data: dict) -> str:
    import yaml

    return yaml.safe_dump(data)
