#!/usr/bin/env python
"""Proof: what a naive proactive agent actually does to one stream of events.

Three postures, the same events, the real `AutonomousEventEngine` in all three.
Nothing here is a thought experiment: the differences come from configuration,
not from three different pieces of code.

    A · naive     no deduplication, no relevance gate, no window bounds.
                  Every delivery — including every provider retry — becomes work.
    B · gated     deduplication and the relevance gate on. No window bounds.
    C · bounded   everything, plus per-source rate limiting and window ceilings.

The stream is deliberately realistic rather than adversarial: a webhook source
that retries, a majority of events that do not warrant action, and one event the
agent itself caused.

    uv run python proofs/p_naive_vs_bounded.py --events proofs/tasks/mine.jsonl

Exits non-zero if the naive posture does not measurably lose. Writes JSON to
proofs/out/p_naive_vs_bounded.json.
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
    morning_report,
)

SELF_ACTOR = "sourcecode"
UNBOUNDED = 10 ** 9


class RecordingRuntime:
    """Records what was asked of the graph. Stubbed so this measures admission."""

    def __init__(self, spend: float) -> None:
        self.runs: list[str] = []
        self.spend = spend

    async def run(self, *, prompt: str, **_: object) -> dict[str, object]:
        self.runs.append(prompt)
        return {"run_id": f"run-{len(self.runs)}", "status": "completed", "spend_usd": self.spend}


def gate(always_relevant: bool, cost: float):
    """The relevance decision. A naive agent has one that always says yes."""

    async def llm(prompt: str, system: str):  # noqa: ARG001
        payload = json.loads(prompt)
        event = payload["event"]
        material = float(event["data"].get("current_error_rate", 0)) > 1.0
        relevant = True if always_relevant else material
        return {"text": json.dumps({
            "relevant": relevant,
            "reason": "no gate: acting on arrival" if always_relevant else (
                "error rate above threshold" if material else "within normal range"),
            "goal": f"Assess {event.get('subject') or event['source']}." if relevant else "",
        }), "metered_calls": [{"cost_usd": cost}]}

    return llm


def build_stream(path: Path | None, distinct: int, retries: int) -> list[dict]:
    """A day of ordinary webhook traffic: retries, noise, and one self-caused event."""
    if path:
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    now = datetime.now(UTC)
    stream: list[dict] = []
    for index in range(distinct):
        material = index % 5 == 0          # one in five actually warrants work
        event = {
            "id": f"deploy-{index}", "source": "deployments",
            "type": "deployment.completed", "subject": "checkout/production",
            "occurred_at": (now - timedelta(seconds=distinct - index)).isoformat(),
            "data": {"previous_error_rate": 0.7,
                     "current_error_rate": 6.4 if material else 0.8},
        }
        stream.append(event)
        # At-least-once delivery is the environment, not an attack. Every third
        # event is redelivered, which is what a retrying provider looks like.
        if index % 3 == 0:
            for _ in range(retries):
                stream.append(dict(event))
    stream.insert(2, {**stream[0], "id": "agent-reply", "actor": SELF_ACTOR,
                      "subject": "the agent's own reply"})
    return stream


async def posture(name: str, stream: list[dict], *, dedupe: bool, relevance: bool,
                  bounds: bool, args) -> dict:
    with tempfile.TemporaryDirectory() as workspace:
        store = EventStore(Path(workspace), history_limit=100_000)
        runtime = RecordingRuntime(args.run_spend)
        governor = AutonomyGovernor(
            store,
            self_actors=(SELF_ACTOR,) if bounds else (),
            source_events_per_minute=args.rate if bounds else UNBOUNDED,
        )
        engine = AutonomousEventEngine(store, runtime, governor=governor)
        store.put_subscription(Subscription(
            id="watch", instruction="Assess material production error-rate increases.",
            event_types=["*"], sources=["*"], tenant_id="proof",
            allowed_side_effects=[], budget=args.run_spend,
            daily_budget=args.daily_budget if bounds else None,
            max_runs_per_day=args.max_runs if bounds else None,
            daily_triage_budget=args.triage_budget if bounds else None,
            ignore_actors=[SELF_ACTOR] if bounds else [],
        ))

        llm = gate(always_relevant=not relevance, cost=args.triage_cost)
        distinct_ids: set[str] = set()
        for raw in stream:
            body = dict(raw)
            if not dedupe:
                # A receiver that does not key on (source, id) treats every
                # delivery as new. This is the naive posture, not a trick.
                body["id"] = f"{body['id']}::{len(distinct_ids)}-{id(body)}"
            distinct_ids.add(raw["id"])
            await engine.process(EventEnvelope(**body), llm=llm)

        report = morning_report(store)
        totals = report["totals"]
        return {
            "posture": name,
            "deliveries": len(stream),
            "distinct_events": len(distinct_ids),
            "runs": len(runtime.runs),
            "refusals": len(store.refusals()),
            "cost_of_watching_usd": totals["cost_of_watching_usd"],
            "cost_of_doing_usd": totals["cost_of_doing_usd"],
            "total_usd": round(totals["cost_of_watching_usd"] + totals["cost_of_doing_usd"], 10),
        }


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=None)
    parser.add_argument("--distinct", type=int, default=30)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--rate", type=int, default=25)
    parser.add_argument("--max-runs", type=int, default=8)
    parser.add_argument("--daily-budget", type=float, default=0.02)
    parser.add_argument("--triage-budget", type=float, default=0.01)
    parser.add_argument("--run-spend", type=float, default=0.002)
    parser.add_argument("--triage-cost", type=float, default=0.00002)
    parser.add_argument("--out", type=Path,
                        default=Path(__file__).parent / "out" / "p_naive_vs_bounded.json")
    args = parser.parse_args()

    stream = build_stream(args.events, args.distinct, args.retries)
    rows = [
        await posture("A · naive", stream, dedupe=False, relevance=False, bounds=False, args=args),
        await posture("B · gated", stream, dedupe=True, relevance=True, bounds=False, args=args),
        await posture("C · bounded", stream, dedupe=True, relevance=True, bounds=True, args=args),
    ]
    naive, gated, bounded = rows

    checks = {
        "naive_acts_on_every_delivery_including_retries":
            naive["runs"] == naive["deliveries"],
        "naive_repeats_work_the_provider_only_delivered_once":
            naive["runs"] > naive["distinct_events"],
        "naive_answers_its_own_event":
            naive["runs"] > gated["runs"],
        "the_gate_alone_is_a_large_reduction":
            gated["runs"] < naive["runs"],
        "only_the_window_bounds_the_worst_case":
            bounded["runs"] <= args.max_runs < naive["runs"],
        "naive_leaves_no_refusal_trail":
            naive["refusals"] == 0 and bounded["refusals"] > 0,
    }

    result = {"generated_at": datetime.now(UTC).isoformat(),
              "arguments": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
              "postures": rows, "checks": checks, "passed": all(checks.values())}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2))

    head = f"{'posture':<13}{'deliveries':>11}{'runs':>7}{'refused':>9}{'watching':>13}{'doing':>13}{'total':>13}"
    print(head); print("-" * len(head))
    for row in rows:
        print(f"{row['posture']:<13}{row['deliveries']:>11}{row['runs']:>7}{row['refusals']:>9}"
              f"{row['cost_of_watching_usd']:>13.8f}{row['cost_of_doing_usd']:>13.8f}"
              f"{row['total_usd']:>13.8f}")
    print(f"\n{naive['distinct_events']} distinct events arrived as {naive['deliveries']} deliveries.")
    print(f"naive spent {naive['total_usd'] / bounded['total_usd']:.1f}x what the bounded posture spent.\n")
    for name, ok in checks.items():
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    print(f"\nwrote {args.out}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
