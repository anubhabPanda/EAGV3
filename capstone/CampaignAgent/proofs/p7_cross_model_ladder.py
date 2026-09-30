#!/usr/bin/env python
"""p7 — the ladder routes across MODELS, and budget pressure walks it down.

The claim this proof exists to defend is the one a "model routing" session cannot
be allowed to fudge. A ladder whose rungs are the same model with different
reasoning budgets is a *throttle*, not a router: a downgrade under pressure buys
a cheaper call, but it never buys a different model, so nothing about model
selection has been demonstrated. Four claims, all read from live calls:

1. **Every rung is a different model.** Ask for each rung by name and the model
   that answers is that rung's configured model, and no two rungs answer with
   the same one.
2. **Pressure downgrades across models.** Ask for the TOP rung with a node
   allowance that only covers a lower rung, and the controller charges the lower
   rung — a different provider and a different model, not the same model asked
   to think less. Repeated for every rung below the top, so the walk down the
   whole ladder is shown, not just its first step.
3. **The rungs are monotone in price.** Projected worst-case cost rises with the
   ladder, which is the only thing that makes "one rung cheaper" meaningful.
4. **The measured spread is real.** The observed dollar cost of the same prompt
   at the top rung, divided by the bottom rung, reported as a multiple.

Nothing here names a provider, a model or a price. The rungs, their models, the
allowances that force each downgrade and the prompt all come from config and
from the command line, so pointing tiers.yaml at a different ladder changes the
numbers rather than breaking the proof.

    python proofs/p7_cross_model_ladder.py --task "<anything>" --base-url http://127.0.0.1:8112
    python proofs/p7_cross_model_ladder.py --task "<anything>" --offline
"""

from __future__ import annotations

from typing import Any

from harness import Args, Proof, economics, main, sync, transport_for

from sourcecode.economics import BudgetedGateway, RunBudget, call_site

#: A neutral instruction. The proof measures which model answered and what it
#: cost, never what it said, so the system prompt only has to be identical
#: across rungs.
SYSTEM = "Answer the user directly and concisely."


def _generous(policy, ladder, input_tokens: int) -> float:
    """A ceiling no rung can exhaust: every rung, several times over."""
    per_call = max(policy.project(ladder.tier(n), input_tokens=input_tokens) for n in ladder.names)
    return per_call * (len(ladder.names) + 2) * 4


def _allowance_landing_on(policy, ladder, target, input_tokens: int) -> float:
    """A node allowance that fits ``target`` and nothing above it.

    Midway between the target rung's projection and the projection of the rung
    directly above it. Derived from the ladder, so it moves when the ladder does.
    """
    above = ladder.names[target.rank + 1]
    below_cost = policy.project(target, input_tokens=input_tokens)
    above_cost = policy.project(ladder.tier(above), input_tokens=input_tokens)
    return (below_cost + above_cost) / 2


async def _scenarios(args: Args, config, transport) -> dict[str, Any]:
    """Every live call this proof makes, in one event loop."""
    ladder, policy = config.ladder, config.policy()
    est = policy.estimate_input_tokens(args.task, SYSTEM)
    gateway_for = lambda budget: BudgetedGateway(  # noqa: E731
        transport, budget=budget, policy=policy, pricing=config.pricing, ladder=ladder
    )

    # --- 1. each rung, asked for by name ---------------------------------- #
    per_rung: dict[str, dict[str, Any]] = {}
    for name in ladder.names:
        budget = RunBudget(
            total=_generous(policy, ladder, est), principal=args.principal, currency=config.pricing.currency
        )
        gateway = gateway_for(budget)
        node = f"rung-{name}"
        try:
            with call_site(node, role=node, tier=name):
                out = await gateway.complete(args.task, SYSTEM)
            per_rung[name] = {
                "requested_tier": name,
                "served_tier": out["tier"],
                "configured_model": ladder.tier(name).model,
                "provider": out["provider"],
                "model": out["model"],
                "cost": out["cost"],
                "input_tokens": out["input_tokens"],
                "output_tokens": out["output_tokens"],
                "text_chars": len(out.get("text") or ""),
                "projected": policy.project(ladder.tier(name), input_tokens=est),
                "decision": out["budget_decision"],
            }
        except Exception as exc:  # a rung that cannot be reached is a real failure
            per_rung[name] = {"requested_tier": name, "error": f"{type(exc).__name__}: {exc}"[:300]}

    # --- 2. the walk down, always ASKING for the top rung ----------------- #
    top = ladder.most_capable
    walk: dict[str, dict[str, Any]] = {}
    for name in ladder.names[:-1]:
        target = ladder.tier(name)
        allowance = _allowance_landing_on(policy, ladder, target, est)
        budget = RunBudget(
            total=_generous(policy, ladder, est), principal=args.principal, currency=config.pricing.currency
        )
        node = f"walk-{name}"
        # The node's slice is the pressure: the run is rich, this node is not,
        # which is exactly what allocation across a live frontier produces.
        budget.reservations[node] = allowance
        gateway = gateway_for(budget)
        try:
            with call_site(node, role=node, tier=top.name):
                out = await gateway.complete(args.task, SYSTEM)
            walk[name] = {
                "requested_tier": top.name,
                "served_tier": out["tier"],
                "allowance": allowance,
                "provider": out["provider"],
                "model": out["model"],
                "cost": out["cost"],
                "decision": out["budget_decision"],
            }
        except Exception as exc:
            walk[name] = {
                "requested_tier": top.name,
                "allowance": allowance,
                "error": f"{type(exc).__name__}: {exc}"[:300],
            }

    return {"est_input_tokens": est, "per_rung": per_rung, "walk": walk}


def run(args: Args) -> Proof:
    config = economics(args)
    ladder, policy = config.ladder, config.policy()
    transport, mode, detail = transport_for(args)
    proof = Proof(name="p7_cross_model_ladder", args=args, mode=mode, mode_detail=detail)

    observed = sync(_scenarios(args, config, transport))
    per_rung, walk = observed["per_rung"], observed["walk"]

    proof.fact("ladder", " < ".join(ladder.names))
    for name in ladder.names:
        row = per_rung[name]
        if "error" in row:
            proof.fact(f"rung {name}", f"FAILED {row['error']}")
            continue
        proof.fact(
            f"rung {name}",
            f"{row['provider']} / {row['model']}  "
            f"projected {row['projected']:.8f}  charged {row['cost']:.8f}  "
            f"{row['input_tokens']}in/{row['output_tokens']}out  {row['text_chars']} chars",
        )
    for name, row in walk.items():
        if "error" in row:
            proof.fact(f"asked {row['requested_tier']}, allowance for {name}", f"FAILED {row['error']}")
            continue
        proof.fact(
            f"asked {row['requested_tier']}, allowance for {name}",
            f"served {row['served_tier']} on {row['provider']} / {row['model']}  "
            f"({row['decision']}, charged {row['cost']:.8f})",
        )

    # 1. every rung answered, on the model config told it to use
    reached = {n: r for n, r in per_rung.items() if "error" not in r}
    proof.check(
        "every rung answered",
        len(reached) == len(ladder.names),
        {n: r.get("error") for n, r in per_rung.items() if "error" in r} or f"{len(reached)} rungs",
    )
    mismatched = {
        n: (r["configured_model"], r["model"])
        for n, r in reached.items()
        if r["configured_model"] and r["model"] != r["configured_model"]
    }
    proof.check(
        "each rung is served by the model its config names",
        not mismatched,
        mismatched or {n: r["model"] for n, r in reached.items()},
    )
    models = [r["model"] for r in reached.values()]
    proof.check(
        "no two rungs are the same model",
        len(set(models)) == len(models),
        sorted(models),
    )
    # Configured providers, not reported ones: the offline transport answers as a
    # single synthetic provider, and this claim is about the ladder rather than
    # about which transport ran it. The reported providers are recorded alongside.
    declared = [ladder.tier(n).request.get("provider") for n in ladder.names]
    proof.check(
        "the rungs are spread across providers, not one provider's menu",
        len({p for p in declared if p}) > 1,
        {
            "configured": dict(zip(ladder.names, declared)),
            "reported": {n: r["provider"] for n, r in reached.items()},
        },
    )
    # every rung must actually have said something: a rung that returns an empty
    # string is a fully billed non-answer, which is the failure mode a thinking
    # model produces when its whole output budget goes to its reasoning channel.
    empty = {n: r["cost"] for n, r in reached.items() if r["text_chars"] == 0}
    proof.check("no rung returns empty text", not empty, empty or f"{len(reached)} rungs answered")

    # 2. the walk down is a change of MODEL at every step
    walked = {n: r for n, r in walk.items() if "error" not in r}
    proof.check(
        "a node allowance below the requested rung is served lower down the ladder",
        walked and all(r["served_tier"] == n for n, r in walked.items()),
        {n: r.get("served_tier") or r.get("error") for n, r in walk.items()},
    )
    proof.check(
        "every downgrade is recorded as one",
        walked and all(r["decision"] in ("downgrade", "branch") for r in walked.values()),
        {n: r["decision"] for n, r in walked.items()},
    )
    top_model = (reached.get(ladder.most_capable.name) or {}).get("model")
    changed = {n: r["model"] for n, r in walked.items() if r["model"] != top_model}
    proof.check(
        "a downgrade changes the MODEL, not just the token budget",
        len(changed) == len(walked) and len(set(changed.values())) == len(changed),
        {"requested_model": top_model, "served_models": changed},
    )

    # 3. monotone projections — what makes "one rung cheaper" mean anything
    projections = [
        policy.project(ladder.tier(n), input_tokens=observed["est_input_tokens"]) for n in ladder.names
    ]
    proof.check(
        "projected cost rises monotonically along the ladder",
        all(b > a for a, b in zip(projections, projections[1:])),
        dict(zip(ladder.names, [round(p, 8) for p in projections])),
    )
    proof.fact(
        "projected spread",
        f"{projections[-1] / projections[0]:.1f}x  ({projections[0]:.8f} -> {projections[-1]:.8f})"
        if projections[0] > 0
        else f"bottom rung projects 0.0 ({projections[-1]:.8f} at the top)",
    )

    # 4. the measured spread, from the charges above
    costs = {n: r["cost"] for n, r in reached.items()}
    cheapest, dearest = (
        costs.get(ladder.names[0]),
        costs.get(ladder.most_capable.name),
    )
    if cheapest and dearest:
        proof.fact("measured spread", f"{dearest / cheapest:.2f}x  ({cheapest:.8f} -> {dearest:.8f})")
        proof.check(
            "the top rung measurably costs more than the bottom rung",
            dearest > cheapest,
            f"{dearest:.8f} > {cheapest:.8f}",
        )
    else:
        proof.fact("measured spread", f"not a multiple: costs {costs}")
        proof.check(
            "the top rung measurably costs more than the bottom rung",
            (dearest or 0.0) > (cheapest or 0.0),
            costs,
        )

    proof.record("observed", observed)
    proof.record("tier_models", {n: ladder.tier(n).model for n in ladder.names})
    return proof


if __name__ == "__main__":
    main(run, __doc__ or "")
