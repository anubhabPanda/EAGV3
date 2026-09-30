#!/usr/bin/env python
"""p2 — a run given a ceiling stays under it.

Three claims, each read out of the ledger rather than off a log line:

1. **The ceiling holds.** Spend never exceeds the declared budget, at any ceiling.
2. **Pressure downgrades.** Given an allowance that cannot cover the tier a node
   asked for, the controller charges a cheaper rung and records that it did.
3. **Exhaustion refuses.** Given a ceiling no tier can fit, no call is made at all.
4. **No unmetered call.** Provider calls and ledger entries agree exactly.

The ceilings for claims 2 and 3 are DERIVED from the configured ladder, not
written down, so editing ``config/tiers.yaml`` changes the numbers rather than
breaking the proof. The ``--budget`` you pass is run as the declared case and
reported alongside.

    python proofs/p2_budget_holds.py --task "<anything>" --budget 0.02
    python proofs/p2_budget_holds.py --task "<anything>" --budget 0.02 --offline
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from harness import Args, Proof, economics, main, run_task, sync, transport_for


async def _all_scenarios(args, scenarios, transport, workspace) -> dict[str, dict]:
    """Every scenario in ONE event loop, so a live transport stays usable."""
    runs: dict[str, dict] = {}
    for index, (label, ceiling) in enumerate(scenarios):
        before_calls, before_failures = transport.calls, transport.failures
        outcome = await run_task(args, budget=ceiling, transport=transport,
                                 data_dir=workspace / f"run{index}")
        budget = outcome.budget
        runs[label] = {
            "ceiling": ceiling,
            "spent": budget.get("spent", 0.0),
            "calls": budget.get("calls", 0),
            "transport_calls": transport.calls - before_calls,
            "transport_failures": transport.failures - before_failures,
            "downgrades": budget.get("downgrades", 0),
            "branches": budget.get("branches", 0),
            "refusals": budget.get("refusals", 0),
            "status": outcome.result.get("status"),
            "tiers_charged": sorted({c["tier"] for c in budget.get("charges", [])}),
            "tiers_requested": sorted({c["requested_tier"] for c in budget.get("charges", [])}),
            "models": sorted({c["model"] for c in budget.get("charges", []) if c.get("model")}),
            "seconds": round(outcome.seconds, 3),
            "run_id": outcome.result["run_id"],
        }
    return runs


def run(args: Args) -> Proof:
    config = economics(args)
    policy = config.policy()
    ladder = config.ladder
    top, cheapest = ladder.most_capable, ladder.cheapest
    reserve = max(1.0 - config.thresholds.reserve_fraction, 1e-9)

    # An allowance between two rungs forces a downgrade; an allowance below the
    # cheapest rung forces a refusal. Both come from the config, not from here.
    below_top = ladder.downgrade(top) or cheapest
    between = (policy.project(below_top) + policy.project(top)) / 2
    scenarios = [
        ("declared", args.budget),
        ("generous", policy.project(top) * len(ladder.names) * 4 / reserve),
        ("tight", between / reserve),
        ("impossible", policy.project(cheapest) / 1000.0),
    ]

    transport, mode, detail = transport_for(args)
    proof = Proof(name="p2_budget_holds", args=args, mode=mode, mode_detail=detail)

    with tempfile.TemporaryDirectory(prefix="s15-p2-") as workspace:
        runs = sync(_all_scenarios(args, scenarios, transport, Path(workspace)))

    for label, record in runs.items():
        proof.fact(label, (
            f"ceiling {record['ceiling']:.8f}  spent {record['spent']:.8f}  "
            f"calls {record['calls']}  downgrades {record['downgrades']}  "
            f"branches {record['branches']}  refusals {record['refusals']}  "
            f"tiers {','.join(record['tiers_charged']) or '-'}"
        ))
    proof.fact("currency", config.pricing.currency)
    proof.fact("ladder", " < ".join(ladder.names))
    proof.fact("models charged", sorted({m for r in runs.values() for m in r["models"]}) or "-")
    failures = sum(record["transport_failures"] for record in runs.values())
    proof.fact("transport failures", f"{failures} (gateway errors; no tokens reported, so not charged)")

    # 1. the ceiling holds, in every scenario
    breaches = {label: (record["spent"], record["ceiling"])
                for label, record in runs.items() if record["spent"] > record["ceiling"]}
    proof.check("no run spends past its ceiling", not breaches, breaches or "0 breaches")

    # 2. a downgrade (or a branch, which also lands on a cheaper rung) is observed
    tight = runs["tight"]
    proof.check("a tight allowance downgrades the tier the node asked for",
                tight["downgrades"] + tight["branches"] > 0,
                f"{tight['downgrades']} downgrades, {tight['branches']} branches, "
                f"requested {tight['tiers_requested']} -> charged {tight['tiers_charged']}")

    # 3. at exhaustion nothing is bought
    impossible = runs["impossible"]
    proof.check("an unaffordable ceiling refuses instead of overspending",
                impossible["calls"] == 0 and impossible["refusals"] > 0 and impossible["spent"] == 0.0,
                f"{impossible['calls']} calls, {impossible['refusals']} refusals, "
                f"spent {impossible['spent']}")

    # 4. no call reached a provider without being metered
    gaps = {label: (record["transport_calls"], record["calls"])
            for label, record in runs.items() if record["transport_calls"] != record["calls"]}
    proof.check("every provider call that returned is metered", not gaps,
                gaps or f"{sum(r['calls'] for r in runs.values())} calls, all charged")

    # 5. the declared run did real work within its ceiling
    declared = runs["declared"]
    proof.check("the declared budget produced a metered run",
                declared["calls"] > 0 and declared["spent"] > 0,
                f"{declared['calls']} calls, spent {declared['spent']:.8f}")

    proof.record("runs", runs)
    return proof


if __name__ == "__main__":
    main(run, __doc__ or "")
