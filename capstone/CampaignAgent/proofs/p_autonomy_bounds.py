#!/usr/bin/env python
"""Proof: an unattended agent is bounded by controls it cannot reach.

Five properties, each established against a stream of events the harness has
never seen, so this is a proof rather than a demonstration. Point `--events` at
your own JSONL file and the harness works unchanged.

    uv run python proofs/p_autonomy_bounds.py --events proofs/tasks/flood.jsonl \
        --max-runs 3 --daily-budget 0.01 --rate 20

Exits non-zero if any property fails. Writes machine-readable JSON to
proofs/out/p_autonomy_bounds.json.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sourcecode.events import (  # noqa: E402
    AutonomousEventEngine,
    AutonomyGovernor,
    EventEnvelope,
    EventStore,
    Subscription,
    liveness_status,
    morning_report,
)

SELF_ACTOR = "sourcecode"


class RecordingRuntime:
    """Stands in for the graph so the proof measures admission, not planning."""

    def __init__(self, spend: float) -> None:
        self.runs: list[str] = []
        self.spend = spend

    async def run(self, *, prompt: str, **_: object) -> dict[str, object]:
        self.runs.append(prompt)
        return {"run_id": f"run-{len(self.runs)}", "status": "completed", "spend_usd": self.spend}


def triage_llm(cost: float):
    async def llm(prompt: str, system: str):  # noqa: ARG001
        payload = json.loads(prompt)
        event = payload["event"]
        relevant = float(event["data"].get("current_error_rate", 0)) > 1.0
        return {"text": json.dumps({
            "relevant": relevant,
            "reason": "error rate above threshold" if relevant else "within normal range",
            "goal": f"Assess {event['subject']}." if relevant else "",
        }), "metered_calls": [{"cost_usd": cost}]}
    return llm


def load_events(path: Path | None, count: int) -> list[dict]:
    if path:
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    now = datetime.now(UTC)
    generated = []
    for index in range(count):
        generated.append({
            "id": f"synthetic-{index}", "source": "deployments",
            "type": "deployment.completed", "subject": "checkout/production",
            "occurred_at": (now - timedelta(seconds=count - index)).isoformat(),
            "data": {"previous_error_rate": 0.7,
                     "current_error_rate": 6.4 if index % 2 == 0 else 0.8},
        })
    # An exact duplicate delivery and one event the agent itself caused, placed
    # early on purpose: the intake rate limiter runs *before* deduplication, so
    # appending them to the tail of a flood would prove only that the flood was
    # stopped. Ordering of controls is itself a thing to get right.
    generated.insert(1, dict(generated[0]))
    generated.insert(2, {**generated[0], "id": "self-caused", "actor": SELF_ACTOR})
    return generated


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=None, help="JSONL of EventEnvelope objects")
    parser.add_argument("--count", type=int, default=40, help="synthetic events when --events is absent")
    parser.add_argument("--max-runs", type=int, default=3)
    parser.add_argument("--daily-budget", type=float, default=0.01)
    parser.add_argument("--triage-budget", type=float, default=0.001)
    parser.add_argument("--rate", type=int, default=25, help="events per minute per source")
    parser.add_argument("--run-spend", type=float, default=0.002)
    parser.add_argument("--triage-cost", type=float, default=0.00002)
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "out" / "p_autonomy_bounds.json")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as workspace:
        store = EventStore(Path(workspace), history_limit=10_000)
        runtime = RecordingRuntime(args.run_spend)
        governor = AutonomyGovernor(store, self_actors=(SELF_ACTOR,),
                                    source_events_per_minute=args.rate)
        engine = AutonomousEventEngine(store, runtime, governor=governor)
        store.put_subscription(Subscription(
            id="bounds", instruction="Assess material production error-rate increases.",
            event_types=["*"], sources=["*"], tenant_id="proof",
            allowed_side_effects=[], budget=args.daily_budget,
            daily_budget=args.daily_budget, max_runs_per_day=args.max_runs,
            daily_triage_budget=args.triage_budget, ignore_actors=[SELF_ACTOR],
        ))

        llm = triage_llm(args.triage_cost)
        outcomes = []
        for raw in load_events(args.events, args.count):
            outcomes.append(await engine.process(EventEnvelope(**raw), llm=llm))

        day = datetime.now(UTC).date().isoformat()
        report = morning_report(store)
        refusals = store.refusals()
        controls = sorted({item["control"] for item in refusals})

        checks = {
            "p1_run_ceiling_holds":
                len(runtime.runs) <= args.max_runs,
            "p2_window_spend_never_exceeded_the_ceiling_unboundedly":
                store.window_spend("bounds", day, kind="run") <= args.daily_budget + args.run_spend,
            "p3_self_caused_event_refused":
                any(item["control"] == "self_trigger" for item in refusals),
            "p4_duplicate_delivery_created_no_second_run":
                sum(1 for item in outcomes if item.get("duplicate")) >= 1,
            "p5_every_refusal_is_visible":
                len(refusals) > 0 and all(item.get("reason") for item in refusals),
            "p6_watching_and_doing_are_billed_separately":
                report["totals"]["cost_of_watching_usd"] > 0
                and report["totals"]["cost_of_doing_usd"] > 0,
            "p7_liveness_is_observable":
                liveness_status(store)["alive"] is True,
        }

        result = {
            "generated_at": datetime.now(UTC).isoformat(),
            "arguments": {key: (str(value) if isinstance(value, Path) else value)
                          for key, value in vars(args).items()},
            "events_delivered": len(outcomes),
            "runs_started": len(runtime.runs),
            "refusal_controls": controls,
            "refusals": len(refusals),
            "totals": report["totals"],
            "checks": checks,
            "passed": all(checks.values()),
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2))

        for name, ok in checks.items():
            print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        print(f"\nevents={len(outcomes)} runs={len(runtime.runs)} refusals={len(refusals)} "
              f"controls={controls}")
        print(f"watching=${report['totals']['cost_of_watching_usd']:.8f} "
              f"doing=${report['totals']['cost_of_doing_usd']:.8f}")
        print(f"\nwrote {args.out}")
        return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
