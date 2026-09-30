#!/usr/bin/env python
"""p3 — an adversarial runaway loop is stopped by the hard controller.

Denial-of-wallet is a security problem, not a billing problem. A bug or an
attacker drives a reasoning loop and nothing stops it; 2026 incident reports cite
more than $47,000 billed over a single weekend. Session 12's invariant 8 said a
loop must be bounded. This is that invariant, priced.

The adversary here is a planner that earns one more node from every outcome,
forever, and asks for the most expensive rung in the ladder each time. It runs
against the real live graph, the real journal and the real controller. What is
being proven is not that the loop is polite, but that it cannot spend:

1. Spend stops at the ceiling however many times the loop goes round.
2. Admitted calls are bounded by the configured call ceiling, which holds even if
   every price estimate were wrong.
3. Refusals are recorded, so an exhausted run is auditable rather than merely dead.
4. No provider call escaped the meter.
5. The bill the same loop would have run up uncontrolled, extrapolated from this
   run's own measured cost per call.

    python proofs/p3_denial_of_wallet.py --task "<anything>" --budget 0.01
    python proofs/p3_denial_of_wallet.py --task "<anything>" --budget 0.01 --offline
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Any

from harness import OUT, Args, Proof, economics, parse, sync, transport_for  # noqa: F401

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sourcecode.core.live_graph import (  # noqa: E402
    Event,
    GraphPatch,
    GraphSnapshot,
    GraphStore,
    LiveGraphExecutor,
    TaskSpec,
)
from sourcecode.economics import (  # noqa: E402
    TIER_KEY,
    BudgetAwarePlanner,
    BudgetedGateway,
)
from sourcecode.runtime import metered  # noqa: E402

#: How many rounds the loop is allowed before the PROOF itself gives up. This is
#: a safety net for the proof, not the thing under test: if the controller worked,
#: spend stopped long before this.
DEFAULT_LOOP_LIMIT = 200
#: Rounds to extrapolate the uncontrolled bill over.
DEFAULT_PROJECTION = 10_000


class RunawayPlanner:
    """The adversary: every outcome earns one more node, at the dearest tier."""

    def __init__(self, task: str, *, skill: str, tier: str, limit: int) -> None:
        self.task, self.skill, self.tier, self.limit = task, skill, tier, limit
        self.rounds = 0
        self.last_selection = {"mode": "adversarial_runaway"}

    def _node(self, index: int) -> TaskSpec:
        return TaskSpec(f"loop_{index}", self.skill,
                        {"query": f"{self.task} (iteration {index})"},
                        {"agent": self.skill, TIER_KEY: self.tier})

    async def plan(self, graph: GraphSnapshot, event: Event) -> GraphPatch:
        if event.kind == "run_started":
            return GraphPatch(add=(self._node(1),), reason="adversary starts the loop")
        if event.kind in ("task_succeeded", "task_failed"):
            self.rounds += 1
            index = len(graph.nodes) + 1
            if self.rounds >= self.limit:
                return GraphPatch(finish=True, reason="proof safety stop; the controller already halted spend")
            return GraphPatch(add=(self._node(index),), reason="adversary spins another iteration")
        return GraphPatch()


async def drive_runaway(args: Args, *, loop_limit: int, data_dir: Path) -> dict[str, Any]:
    """Run the adversarial loop against the real graph and the real controller."""
    config = economics(args)
    transport, mode, detail = transport_for(args)
    store = GraphStore(data_dir / "graph.sqlite")
    run_id = "runaway"
    budget = config.budget(principal=args.principal, amount=args.budget, run_id=run_id)
    gateway = BudgetedGateway(transport, budget=budget, policy=config.policy(),
                              pricing=config.pricing, ladder=config.ladder)
    llm = gateway.as_text_llm()

    async def work(task: TaskSpec) -> dict[str, Any]:
        """One adversarial step. It does nothing but try to spend."""
        result = await llm(task.input["query"], "Reply briefly. This is a controlled loop test.")
        return {"text": result.get("text", ""), "provider": result.get("provider"),
                "model": result.get("model"), "tier": result.get("tier")}

    planner = BudgetAwarePlanner(
        inner=RunawayPlanner(args.task, skill="content", tier=config.ladder.most_capable.name,
                             limit=loop_limit),
        ladder=config.ladder, budget=budget,
        reserve_fraction=config.thresholds.reserve_fraction,
    )
    store.start(run_id, context={"prompt": args.task})
    try:
        report = await LiveGraphExecutor(store, planner, {"content": metered(work)},
                                         max_workers=1).run(run_id)
        snapshot = store.snapshot(run_id)
        journal = [{"sequence": e.sequence, "kind": e.kind, "node_id": e.node_id, "payload": e.payload}
                   for e in store.events(run_id)]
    finally:
        store.close()
    return {
        "mode": mode, "mode_detail": detail, "config": config,
        "budget": budget.snapshot(), "transport_calls": transport.calls,
        "transport_failures": transport.failures, "transport_errors": transport.errors[:5],
        "nodes": len(snapshot.nodes), "rounds": planner.inner.rounds, "finished": report.finished,
        "journal": journal,
        "failed_nodes": sum(1 for node in snapshot.nodes.values() if node["state"] == "failed"),
        "refused_nodes": sum(
            1 for node in snapshot.nodes.values()
            if node["state"] == "failed" and "BudgetRefused" in str((node.get("result") or {}).get("error", ""))
        ),
    }


def run(args: Args, *, loop_limit: int, projection: int) -> Proof:
    with tempfile.TemporaryDirectory(prefix="s15-p3-") as workspace:
        outcome = sync(drive_runaway(args, loop_limit=loop_limit, data_dir=Path(workspace)))

    config = outcome["config"]
    budget = outcome["budget"]
    proof = Proof(name="p3_denial_of_wallet", args=args, mode=outcome["mode"],
                  mode_detail=outcome["mode_detail"])

    cost_per_call = budget["spent"] / budget["calls"] if budget["calls"] else 0.0
    uncontrolled = cost_per_call * projection

    proof.fact("ceiling", f"{budget['total']:.8f} {budget['currency']}")
    proof.fact("spent", f"{budget['spent']:.8f}")
    proof.fact("admitted calls", budget["calls"])
    proof.fact("refusals", budget["refusals"])
    proof.fact("loop rounds", outcome["rounds"])
    proof.fact("nodes created", outcome["nodes"])
    proof.fact("refused nodes", outcome["refused_nodes"])
    proof.fact("cost per call", f"{cost_per_call:.8f}")
    proof.fact("uncontrolled bill", f"~{uncontrolled:.4f} over {projection} rounds (extrapolated)")
    proof.fact("call ceiling", config.thresholds.max_calls_per_run)
    proof.fact("transport failures", outcome["transport_failures"])

    proof.check("the ceiling held under an unbounded loop",
                budget["spent"] <= budget["total"],
                f"spent {budget['spent']:.8f} <= {budget['total']:.8f}")
    proof.check("admitted calls are bounded by the configured call ceiling",
                config.thresholds.max_calls_per_run == 0
                or budget["calls"] <= config.thresholds.max_calls_per_run,
                f"{budget['calls']} <= {config.thresholds.max_calls_per_run}")
    proof.check("the loop kept asking and was refused",
                budget["refusals"] > 0 and outcome["rounds"] > budget["calls"],
                f"{outcome['rounds']} rounds, {budget['calls']} admitted, {budget['refusals']} refused")
    proof.check("a refusal is a visible graph failure, not a silent truncation",
                outcome["refused_nodes"] > 0,
                f"{outcome['refused_nodes']} nodes failed with BudgetRefused")
    proof.check("every provider call that returned is metered",
                outcome["transport_calls"] == budget["calls"],
                f"{outcome['transport_calls']} transport calls == {budget['calls']} charges "
                f"({outcome['transport_failures']} gateway errors, no tokens to charge)")
    proof.check("the controller, not the loop, is what stopped the spend",
                budget["calls"] < outcome["rounds"],
                f"spend stopped after {budget['calls']} of {outcome['rounds']} attempts")

    proof.record("budget", budget)
    proof.record("journal_events", len(outcome["journal"]))
    proof.record("projection_rounds", projection)
    proof.record("uncontrolled_bill_extrapolated", uncontrolled)
    return proof


def main() -> None:
    extra = argparse.ArgumentParser(add_help=False)
    extra.add_argument("--loop-limit", type=int, default=DEFAULT_LOOP_LIMIT)
    extra.add_argument("--projection-rounds", type=int, default=DEFAULT_PROJECTION)
    known, rest = extra.parse_known_args()
    args = parse(__doc__ or "", rest)
    sys.exit(run(args, loop_limit=known.loop_limit, projection=known.projection_rounds).finish())


if __name__ == "__main__":
    main()
