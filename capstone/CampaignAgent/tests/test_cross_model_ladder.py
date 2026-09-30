"""The shipped ladder must be cross-MODEL, and a downgrade must change the model.

`test_economics.py` already proves the ladder machinery works on a synthetic
ladder with invented names, which is the right way to prove the code does not
depend on config. These tests do the opposite job: they pin the ladder actually
shipped in `config/`, because a ladder whose rungs are all the same model turns
every routing claim in the session into a claim about reasoning effort.

Nothing here names a model or a provider. Every assertion is read out of the
config, so repointing a rung changes what is asserted rather than breaking it.
"""

from __future__ import annotations

import pytest
import yaml

from sourcecode.economics import BudgetedGateway, EconomicsConfig, RunBudget, call_site


@pytest.fixture
def config() -> EconomicsConfig:
    return EconomicsConfig.load()


def test_every_rung_declares_a_different_model(config):
    models = [config.ladder.tier(name).model for name in config.ladder.names]
    assert all(models), models
    assert len(set(models)) == len(models), models


def test_every_rung_declares_a_provider_and_they_are_not_all_the_same(config):
    providers = [config.ladder.tier(n).request.get("provider") for n in config.ladder.names]
    assert all(providers), providers
    assert len(set(providers)) > 1, providers


def test_every_rung_has_a_real_price_row(config):
    """A rung priced by the fallback row is a rung nobody measured."""
    for name in config.ladder.names:
        model = config.ladder.tier(name).model
        assert model in config.pricing.models, f"{name} -> {model} has no row in pricing.yaml"


def test_the_cheapest_rung_costs_something(config):
    """A free rung cannot be exhausted by a dollar ceiling, so `refuse at
    exhaustion` would stop being expressible in money and fall entirely to the
    call-count ceiling. Both bounds should hold, so the bottom rung is priced."""
    assert config.policy().project(config.ladder.cheapest) > 0


def test_projected_cost_rises_monotonically_along_the_ladder(config):
    policy = config.policy()
    costs = [policy.project(config.ladder.tier(n)) for n in config.ladder.names]
    assert costs == sorted(costs), dict(zip(config.ladder.names, costs))
    assert len(set(costs)) == len(costs), costs


def test_rates_themselves_rise_along_the_ladder(config):
    """Monotone projections could also be bought with max_tokens alone. The rungs
    have to be ordered by PRICE PER TOKEN too, or "cheaper rung" only means
    "shorter answer"."""
    for cheaper, dearer in zip(config.ladder.names, config.ladder.names[1:]):
        lo = config.pricing.price_for(config.ladder.tier(cheaper).model)
        hi = config.pricing.price_for(config.ladder.tier(dearer).model)
        assert lo.input <= hi.input, (cheaper, dearer)
        assert lo.output <= hi.output, (cheaper, dearer)
        assert (lo.input, lo.output) != (hi.input, hi.output), (cheaper, dearer)


def test_a_thinking_rung_asks_for_the_reasoning_dial_off(config):
    """Measured: the models on this ladder that think by default return an empty
    string at full price when their output budget goes to the reasoning channel.
    pricing.yaml records which ones; any rung on such a model must send the dial.
    """
    raw = yaml.safe_load((config.directory / "pricing.yaml").read_text(encoding="utf-8"))
    needs_off = {
        model
        for model, row in (raw.get("models") or {}).items()
        if isinstance(row, dict) and row.get("measured_needs_reasoning_off")
    }
    assert needs_off, "pricing.yaml records no measured thinking models; did the annotation move?"
    for name in config.ladder.names:
        tier = config.ladder.tier(name)
        if tier.model in needs_off:
            assert tier.request.get("reasoning") == "off", f"{name} ({tier.model}) must ask for reasoning off"


class _RecordingTransport:
    """Answers as whatever model the request asked for, and remembers the asks."""

    def __init__(self):
        self.requests: list[dict] = []

    async def chat(self, *, prompt, system, request=None):
        request = dict(request or {})
        self.requests.append(request)
        return {
            "text": "ok",
            "provider": request.get("provider"),
            "model": request.get("model"),
            "input_tokens": 10,
            "output_tokens": int(request.get("max_tokens") or 10),
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "latency_ms": 1.0,
        }


def _generous(config, policy) -> float:
    top = policy.project(config.ladder.most_capable)
    return top * (len(config.ladder.names) + 2) * 4


@pytest.mark.asyncio
async def test_asking_for_a_rung_calls_that_rungs_model(config):
    policy, transport = config.policy(), _RecordingTransport()
    for name in config.ladder.names:
        budget = RunBudget(total=_generous(config, policy))
        gateway = BudgetedGateway(
            transport, budget=budget, policy=policy, pricing=config.pricing, ladder=config.ladder
        )
        with call_site(f"n-{name}", role=f"n-{name}", tier=name):
            out = await gateway.complete("q", "s")
        assert out["tier"] == name
        assert out["model"] == config.ladder.tier(name).model
        assert out["provider"] == config.ladder.tier(name).request.get("provider")


@pytest.mark.asyncio
async def test_pressure_downgrades_to_a_different_model_at_every_rung(config):
    """The headline. Ask for the top rung with a node allowance that only covers
    a lower rung, and the call that goes out names the LOWER rung's model."""
    policy, transport = config.policy(), _RecordingTransport()
    top = config.ladder.most_capable
    served: dict[str, str] = {}
    for name in config.ladder.names[:-1]:
        target = config.ladder.tier(name)
        above = config.ladder.tier(config.ladder.names[target.rank + 1])
        allowance = (policy.project(target) + policy.project(above)) / 2
        budget = RunBudget(total=_generous(config, policy))
        node = f"walk-{name}"
        budget.reservations[node] = allowance
        gateway = BudgetedGateway(
            transport, budget=budget, policy=policy, pricing=config.pricing, ladder=config.ladder
        )
        with call_site(node, role=node, tier=top.name):
            out = await gateway.complete("q", "s")
        assert out["tier"] == name, (name, out["tier"])
        assert out["budget_decision"] in ("downgrade", "branch")
        assert out["model"] != top.model, "a downgrade that keeps the model is a throttle, not a route"
        served[name] = out["model"]
    assert len(set(served.values())) == len(served), served
