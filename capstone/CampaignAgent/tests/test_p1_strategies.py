"""p1's strategy derivation and arithmetic, tested against ladders it has never seen.

The claim p1 rests on is that it reads the tier ladder from config at run time and
never names a rung. So the tests hand it invented ladders — two rungs, five rungs,
renamed rungs, a reordered ladder — and check that the three strategies still land
on the right ends of it, that escalation walks it one step at a time, and that the
headline arithmetic (cost per resolved task, and the finding derived from it) is
what it claims to be.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "proofs"))

from p1_cost_per_task import (  # noqa: E402
    SimulatedGateway,
    break_even_resolution_rate,
    finding,
    start_tier,
    strategies_for,
    summarise,
)

from sourcecode.economics import EconomicsConfig, TierLadder  # noqa: E402
from sourcecode.evals import EvalsConfig  # noqa: E402

CONFIG_DIR = ROOT / "config"


def ladder(*names: str) -> TierLadder:
    """An invented ladder: rung names and providers no module has heard of."""
    return TierLadder.from_mapping({
        "order": list(names),
        "default_tier": names[len(names) // 2],
        "role_tiers": {"default": names[len(names) // 2]},
        "tiers": {
            name: {
                "request": {"provider": f"provider_{index}", "model": f"model-{name}",
                            "max_tokens": 256 * (index + 1)},
                "projected_input_tokens": 100 * (index + 1),
                "projected_output_tokens": 100 * (index + 1),
            }
            for index, name in enumerate(names)
        },
    })


def config_with(rungs: TierLadder) -> EconomicsConfig:
    from dataclasses import replace

    return replace(EconomicsConfig.load(CONFIG_DIR), ladder=rungs)


def evals_with(**strategy_overrides) -> EvalsConfig:
    from dataclasses import replace

    loaded = EvalsConfig.load(CONFIG_DIR)
    if not strategy_overrides:
        return loaded
    return replace(loaded, strategies=replace(loaded.strategies, **strategy_overrides))


# --------------------------------------------------------------------------- #
# the strategies come from the ladder, never from Python
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("names", [
    ("tin", "brass"),
    ("cheap", "mid", "dear"),
    ("r0", "r1", "r2", "r3", "r4"),
])
def test_the_baselines_land_on_the_ends_of_whatever_ladder_is_configured(names):
    built = strategies_for(config_with(ladder(*names)), evals_with(start="cheapest"))
    assert built["A"].start_tier == names[-1], "always-frontier takes the top rung"
    assert built["B"].start_tier == names[0], "always-cheapest takes the bottom rung"
    assert built["C"].start_tier == names[0]
    assert built["A"].attempts == 1 and built["A"].escalate is False
    assert built["B"].escalate is False, "the cheap baseline retries, it does not escalate"


def test_a_one_rung_ladder_collapses_the_strategies_rather_than_crashing():
    built = strategies_for(config_with(ladder("only")), evals_with())
    assert {strategy.start_tier for strategy in built.values()} == {"only"}


def test_the_budget_aware_opening_rung_is_config():
    rungs = ladder("a", "b", "c", "d")
    assert start_tier(rungs, "cheapest") == "a"
    assert start_tier(rungs, "most_capable") == "d"
    assert start_tier(rungs, "default") == rungs.default.name
    assert start_tier(rungs, "role") == rungs.for_role("anything-at-all").name
    assert start_tier(rungs, "c") == "c", "an explicit rung name is honoured"
    with pytest.raises(SystemExit, match="neither a keyword"):
        start_tier(rungs, "no-such-rung")


def test_escalation_climbs_one_rung_and_stops_at_the_top():
    rungs = ladder("one", "two", "three")
    cascade = strategies_for(config_with(rungs), evals_with(start="cheapest", escalate=True))["C"]
    assert cascade.next_tier(rungs, "one") == "two"
    assert cascade.next_tier(rungs, "two") == "three"
    assert cascade.next_tier(rungs, "three") == "three", "the top rung is the ceiling"

    retrying = strategies_for(config_with(rungs), evals_with(start="cheapest", escalate=False))["C"]
    assert retrying.next_tier(rungs, "one") == "one", "without escalation the rung never moves"


def test_the_cheap_baselines_attempt_count_is_the_configured_retry_policy():
    rungs = ladder("lo", "hi")
    generous = strategies_for(config_with(rungs), evals_with(max_attempts=9, cheapest_retries=4))
    assert generous["B"].attempts == 5, "one attempt plus the configured retries"
    capped = strategies_for(config_with(rungs), evals_with(max_attempts=2, cheapest_retries=7))
    assert capped["B"].attempts == 2, "max_attempts is a hard ceiling"
    once = strategies_for(config_with(rungs), evals_with(max_attempts=1, cheapest_retries=0))
    assert once["B"].attempts == 1, "with no retries the cheap baseline is not a trap at all"


# --------------------------------------------------------------------------- #
# the arithmetic
# --------------------------------------------------------------------------- #


def row(task_id, *, cost, calls, resolved, status=None, difficulty="hard", tokens=100):
    return {
        "task_id": task_id, "difficulty": difficulty, "strategy": "X",
        "attempts": [{"error": None, "answer_chars": 10, "model": "model-x"}] * calls,
        "attempt_count": calls, "resolved": resolved,
        "status": status or ("resolved" if resolved else "unresolved"),
        "cost": cost, "calls": calls, "input_tokens": tokens, "output_tokens": tokens,
        "latency_ms": 1.0, "tiers_charged": ["lo"] * calls, "models": ["model-x"],
        "downgrades": 0, "branches": 0, "refusals": 0, "overall": 1.0 if resolved else 0.2,
        "agreement": 1.0, "self_judged": False, "verdict": None,
    }


def test_cost_per_resolved_task_is_spend_over_resolved_not_over_tasks():
    strategy = strategies_for(config_with(ladder("lo", "hi")), evals_with())["B"]
    rows = [row("t1", cost=1.0, calls=1, resolved=True), row("t2", cost=3.0, calls=3, resolved=False)]
    out = summarise(rows, strategy)
    assert out["spend"] == 4.0 and out["calls"] == 4
    assert out["cost_per_call"] == 1.0
    assert out["cost_per_task"] == 2.0
    assert out["cost_per_resolved_task"] == 4.0, "the failed task's spend still counts"
    assert out["resolution_rate"] == 0.5
    assert out["tokens_per_resolved_task"] == 400


def test_a_strategy_that_resolves_nothing_reports_no_cost_per_resolved_task():
    strategy = strategies_for(config_with(ladder("lo", "hi")), evals_with())["B"]
    out = summarise([row("t1", cost=1.0, calls=3, resolved=False)], strategy)
    assert out["resolved"] == 0
    assert out["cost_per_resolved_task"] is None, "never divide by zero and call it a number"


def test_judge_failures_are_counted_apart_from_unresolved():
    strategy = strategies_for(config_with(ladder("lo", "hi")), evals_with())["B"]
    rows = [
        row("t1", cost=1.0, calls=1, resolved=False, status="unresolved"),
        row("t2", cost=1.0, calls=1, resolved=False, status="judge_failed"),
    ]
    out = summarise(rows, strategy)
    assert out["unresolved"] == 1 and out["judge_failed"] == 1


def test_the_signature_failure_mode_is_detected_when_both_halves_hold():
    summaries = {
        "A": {"cost_per_call": 0.010, "cost_per_resolved_task": 0.010, "resolved": 10,
              "resolution_rate": 1.0},
        "B": {"cost_per_call": 0.002, "cost_per_resolved_task": 0.020, "resolved": 3,
              "resolution_rate": 0.3},
    }
    result = finding(summaries)
    assert result["observed"] is True
    comparison = result["comparisons"]["B_vs_A"]
    assert comparison["cost_per_call_delta_pct"] == pytest.approx(-80.0)
    assert comparison["cost_per_resolved_task_delta_pct"] == pytest.approx(100.0)


def test_cheaper_on_both_measures_is_reported_as_NOT_observed():
    """The honest negative: a cheap rung that also wins per resolved task."""
    summaries = {
        "A": {"cost_per_call": 0.010, "cost_per_resolved_task": 0.010, "resolved": 10,
              "resolution_rate": 1.0},
        "B": {"cost_per_call": 0.002, "cost_per_resolved_task": 0.004, "resolved": 9,
              "resolution_rate": 0.9},
    }
    result = finding(summaries)
    assert result["observed"] is False
    assert result["comparisons"]["B_vs_A"]["cheaper_per_call"] is True
    assert result["comparisons"]["B_vs_A"]["dearer_per_resolved_task"] is False


def test_a_cheap_rung_that_resolves_nothing_is_flagged_as_unbounded():
    summaries = {
        "A": {"cost_per_call": 0.010, "cost_per_resolved_task": 0.010, "resolved": 10,
              "resolution_rate": 1.0},
        "B": {"cost_per_call": 0.002, "cost_per_resolved_task": None, "resolved": 0,
              "resolution_rate": 0.0},
    }
    result = finding(summaries)
    assert result["observed_unbounded"] is True
    assert "infinite" in result["comparisons"]["B_vs_A"]["note"]


def test_the_break_even_resolution_rate_is_where_the_two_measures_cross():
    """Below the break-even rate the trap appears; above it the cheap rung just wins."""
    cheap_per_call, attempts = 0.001, 3
    rate = break_even_resolution_rate(
        cheap_cost_per_call=cheap_per_call, dear_cost_per_resolved=0.010, attempts=attempts
    )
    assert rate == pytest.approx(3 / (10 - 1 + 3))

    # At exactly the break-even rate the two costs per resolved task agree.
    at_break_even = cheap_per_call * (rate + (1 - rate) * attempts) / rate
    assert at_break_even == pytest.approx(0.010)
    # A wider price spread pushes the trap further out of reach.
    wider = break_even_resolution_rate(
        cheap_cost_per_call=cheap_per_call, dear_cost_per_resolved=0.100, attempts=attempts
    )
    assert wider < rate
    # With no retries at all there is no trap to find: one call each, cheaper wins.
    assert break_even_resolution_rate(
        cheap_cost_per_call=cheap_per_call, dear_cost_per_resolved=0.010, attempts=1
    ) == pytest.approx(1 / 10)
    assert break_even_resolution_rate(
        cheap_cost_per_call=None, dear_cost_per_resolved=0.01, attempts=3) is None
    assert break_even_resolution_rate(
        cheap_cost_per_call=0.01, dear_cost_per_resolved=None, attempts=3) is None


def test_the_finding_reports_the_break_even_beside_the_measurement():
    summaries = {
        "A": {"cost_per_call": 0.010, "cost_per_resolved_task": 0.010, "resolved": 12,
              "resolution_rate": 1.0, "max_attempts": 1},
        "B": {"cost_per_call": 0.001, "cost_per_resolved_task": 0.001, "resolved": 12,
              "resolution_rate": 1.0, "max_attempts": 3},
    }
    result = finding(summaries)
    assert result["observed"] is False, "the cheap rung won on both measures"
    row = result["comparisons"]["B_vs_A"]
    assert row["break_even_resolution_rate"] == pytest.approx(0.25)
    assert row["headroom_above_break_even"] == pytest.approx(0.75)


def test_no_comparison_is_invented_when_the_cheap_baseline_did_not_run():
    assert finding({"A": {"cost_per_call": 1.0, "cost_per_resolved_task": 1.0, "resolved": 1,
                          "resolution_rate": 1.0}})["observed"] is None


# --------------------------------------------------------------------------- #
# offline mode is a simulation, and says so
# --------------------------------------------------------------------------- #


async def test_the_offline_stand_in_reads_the_criteria_out_of_the_schema():
    """Renaming a criterion in evals.yaml must not break offline mode either."""
    gateway = SimulatedGateway()
    invented = ["wibble", "wobble"]
    verdict = await gateway.chat(
        prompt="sufficient=1", system="",
        request={"model": "m", "response_format": {
            "schema": {"properties": {"scores": {"required": invented}}}}},
    )
    assert sorted(json.loads(verdict["text"])["scores"]) == sorted(invented)
    assert gateway.simulated is True


async def test_the_offline_stand_in_makes_a_bigger_rung_answer_more_tasks():
    gateway = SimulatedGateway()
    prompts = [f"task number {index}" for index in range(40)]
    small = [await gateway.chat(prompt=p, system="", request={"max_tokens": 300}) for p in prompts]
    large = [await gateway.chat(prompt=p, system="", request={"max_tokens": 4096}) for p in prompts]
    sufficient = lambda replies: sum("sufficient=1" in r["text"] for r in replies)  # noqa: E731
    assert sufficient(small) < sufficient(large)
    # And it respects the rung's output ceiling, so the ledger arithmetic is real.
    assert all(reply["output_tokens"] <= 300 for reply in small)
