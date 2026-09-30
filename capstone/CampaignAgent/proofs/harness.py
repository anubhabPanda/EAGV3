"""The shared proof harness: arguments, transports, runs, assertions, output.

Every proof in this directory takes the task, the budget and the principal as
command-line arguments and runs the same library code path. Nothing here knows
what the task is about, so a reviewer can point any proof at a task it has never
seen and watch it work with no edit.

Two modes, one code path:

``live``     the gateway at ``--base-url`` is reachable, so real provider calls
             are made, real tokens are counted and real money is metered.
``offline``  a deterministic transport stands in for the gateway. The controller,
             the policy, the ladder, the journal and the span export are all the
             real thing; only the network is replaced. That is what lets CI run
             the same proof with no key and no collector.

Semantic-memory embeddings run through a deterministic embedder by default. The
proofs measure economics and traces, not retrieval quality, and a local Ollama
should not decide whether a budget invariant holds. Pass ``--live-embeddings`` to
use the real embedder.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from sourcecode.core.memory import MemoryScope  # noqa: E402
from sourcecode.core.memory.embeddings import DeterministicEmbedder  # noqa: E402
from sourcecode.economics import EconomicsConfig, MeteredTransport  # noqa: E402
from sourcecode.gateway import GatewayClient  # noqa: E402
from sourcecode.runtime import AgentRuntime  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
DEFAULT_BASE_URL = os.getenv("GLC_BASE_URL", "http://127.0.0.1:8111")


# --------------------------------------------------------------------------- #
# arguments
# --------------------------------------------------------------------------- #


@dataclass
class Args:
    task: str
    budget: float
    principal: str
    offline: bool
    base_url: str
    otel_endpoint: str | None
    respond_as: str
    config_dir: str | None
    live_embeddings: bool
    label: str

    @property
    def scope(self) -> MemoryScope:
        """A memory scope for this principal. The principal IS the attribution."""
        parts = (self.principal.split("/") + ["", "", ""])[:4]
        return MemoryScope(parts[0] or "proofs", parts[1] or None, parts[2] or None, parts[3] or None)


def parse(description: str, argv: list[str] | None = None) -> Args:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--task", required=True,
                        help="the task to run. Any task: the harness knows nothing about it.")
    parser.add_argument("--budget", type=float, default=None,
                        help="the run ceiling, in the currency named by pricing.yaml")
    parser.add_argument("--principal", default="proofs/s15/reviewer",
                        help="who the spend attributes to (tenant/project/user/agent)")
    parser.add_argument("--offline", action="store_true",
                        help="use the deterministic transport instead of a live gateway")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--otel-endpoint", default=os.getenv("S17_OTEL_EXPORTER_ENDPOINT"),
                        help="OTLP endpoint. Unset means build the spans and send nothing.")
    parser.add_argument("--respond-as", default="text", choices=("text", "ui"))
    parser.add_argument("--config-dir", default=os.getenv("S17_CONFIG_DIR"))
    parser.add_argument("--live-embeddings", action="store_true")
    parser.add_argument("--label", default="", help="suffix for the JSON written to proofs/out/")
    parsed = parser.parse_args(argv)
    config = EconomicsConfig.load(parsed.config_dir)
    return Args(
        task=parsed.task,
        budget=parsed.budget if parsed.budget is not None else config.default_budget,
        principal=parsed.principal,
        offline=parsed.offline,
        base_url=parsed.base_url.rstrip("/"),
        otel_endpoint=parsed.otel_endpoint or None,
        respond_as=parsed.respond_as,
        config_dir=parsed.config_dir,
        live_embeddings=parsed.live_embeddings,
        label=parsed.label,
    )


def economics(args: Args) -> EconomicsConfig:
    return EconomicsConfig.load(args.config_dir)


# --------------------------------------------------------------------------- #
# transports
# --------------------------------------------------------------------------- #


class OfflineTransport:
    """A deterministic stand-in for the gateway.

    Faithful in the two ways the controller's arithmetic depends on: input tokens
    scale with the prompt it was handed, and output respects the ``max_tokens``
    the tier asked for. Everything above it — policy, ladder, budget, journal,
    spans — is the real implementation.
    """

    def __init__(self, *, wanted_output: int = 4000, latency_ms: float = 8.0) -> None:
        self.wanted_output, self.latency_ms = wanted_output, latency_ms

    async def chat(self, *, prompt: str, system: str, request: dict[str, Any] | None = None) -> dict[str, Any]:
        request = dict(request or {})
        ceiling = int(request.get("max_tokens") or self.wanted_output)
        digest = hashlib.sha256((prompt + system).encode()).hexdigest()[:12]
        return {
            "text": json.dumps({"offline": True, "digest": digest,
                                "note": "deterministic offline transport; no provider was called"}),
            "provider": "offline_1",
            "model": request.get("model", "offline-model"),
            "input_tokens": len(prompt) // 4 + len(system) // 4,
            "output_tokens": min(self.wanted_output, ceiling),
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "latency_ms": self.latency_ms,
        }


def gateway_reachable(base_url: str, *, timeout: float = 2.0) -> bool:
    try:
        return httpx.get(f"{base_url}/healthz", timeout=timeout).status_code == 200
    except Exception:
        return False


def transport_for(args: Args) -> tuple[MeteredTransport, str, dict[str, Any]]:
    """The transport, the mode it represents, and how the choice was made.

    Wrapping in :class:`MeteredTransport` is what makes "no unmetered call"
    checkable: the wrapper counts every call that reached a provider, and the
    proof compares that count against the budget ledger.
    """
    if not args.offline and gateway_reachable(args.base_url):
        return MeteredTransport(GatewayClient(args.base_url)), "live", {"base_url": args.base_url}
    reason = "--offline requested" if args.offline else f"gateway at {args.base_url} is not reachable"
    return MeteredTransport(OfflineTransport()), "offline", {"reason": reason}


# --------------------------------------------------------------------------- #
# running a task
# --------------------------------------------------------------------------- #


@dataclass
class RunResult:
    result: dict[str, Any]
    transport_calls: int
    transport_failures: int
    seconds: float

    @property
    def budget(self) -> dict[str, Any]:
        return self.result.get("budget") or {}

    @property
    def journal(self) -> dict[str, Any]:
        """The run in the shape every consumer reads: graph replay, UI, traces."""
        graph = self.result.get("graph") or {}
        return {
            "run_id": self.result["run_id"],
            "finished": graph.get("finished", False),
            "nodes": graph.get("nodes") or {},
            "edges": graph.get("edges") or (),
            "events": [
                {"sequence": e["sequence"], "kind": e["kind"], "node_id": e.get("node_id"),
                 "payload": e.get("payload") or {}}
                for e in self.result.get("events") or []
            ],
        }


def runtime_for(args: Args, data_dir: Path) -> AgentRuntime:
    runtime = AgentRuntime(root=data_dir)
    if not args.live_embeddings:
        runtime.memory.embedder = DeterministicEmbedder(128)
    return runtime


async def run_task(
    args: Args,
    *,
    budget: float | None,
    transport: MeteredTransport,
    data_dir: Path,
    task: str | None = None,
) -> RunResult:
    """Run one task through the real runtime, optionally with a ceiling."""
    runtime = runtime_for(args, data_dir)
    started = time.time()
    try:
        result = await runtime.run(
            prompt=task or args.task,
            scope=args.scope,
            source_uri="proof://harness",
            source_author="proof-harness",
            respond_as=args.respond_as,
            budget=budget,
            principal=args.principal,
            transport=transport,
            economics=economics(args),
        )
    finally:
        runtime.close()
    return RunResult(result=result, transport_calls=transport.calls,
                     transport_failures=transport.failures, seconds=time.time() - started)


def sync(coro) -> Any:
    """Run one coroutine. Call this ONCE per proof.

    A live transport holds an httpx client bound to the loop it was first used on,
    so every scenario a proof wants must await inside the same coroutine.
    """
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# assertions and output
# --------------------------------------------------------------------------- #


@dataclass
class Proof:
    """Collects checks, writes machine-readable JSON, prints a human table."""

    name: str
    args: Args
    mode: str
    mode_detail: dict[str, Any] = field(default_factory=dict)
    checks: list[dict[str, Any]] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)
    detail: dict[str, Any] = field(default_factory=dict)

    def check(self, claim: str, ok: bool, observed: Any = None) -> bool:
        self.checks.append({"claim": claim, "ok": bool(ok), "observed": observed})
        return bool(ok)

    def fact(self, key: str, value: Any) -> None:
        """A number for the human table (and the JSON)."""
        self.facts[key] = value

    def record(self, key: str, value: Any) -> None:
        """Machine-readable detail for the JSON only; too big for the table."""
        self.detail[key] = value

    @property
    def ok(self) -> bool:
        return all(check["ok"] for check in self.checks)

    def payload(self) -> dict[str, Any]:
        return {
            "proof": self.name,
            "ok": self.ok,
            "mode": self.mode,
            "mode_detail": self.mode_detail,
            "arguments": {
                "task": self.args.task, "budget": self.args.budget, "principal": self.args.principal,
                "respond_as": self.args.respond_as, "otel_endpoint": self.args.otel_endpoint,
            },
            "economics": economics(self.args).describe(),
            "facts": self.facts,
            "checks": self.checks,
            "detail": self.detail,
        }

    def finish(self) -> int:
        OUT.mkdir(parents=True, exist_ok=True)
        suffix = f"_{self.args.label}" if self.args.label else ""
        path = OUT / f"{self.name}{suffix}.json"
        path.write_text(json.dumps(self.payload(), indent=2, default=str), encoding="utf-8")

        width = max([len(check["claim"]) for check in self.checks] + [len(key) for key in self.facts] + [10])
        print(f"\n{self.name}  ({self.mode} mode)")
        print(f"  task      {self.args.task}")
        print(f"  budget    {self.args.budget}  principal {self.args.principal}")
        if self.mode_detail:
            print(f"  transport {json.dumps(self.mode_detail)}")
        print()
        for key, value in self.facts.items():
            print(f"  {key:<{width}}  {value}")
        print()
        for check in self.checks:
            mark = "PASS" if check["ok"] else "FAIL"
            print(f"  [{mark}] {check['claim']:<{width}}  {check['observed']}")
        print(f"\n  {'ALL CHECKS PASSED' if self.ok else 'FAILED'} -> {path}\n")
        return 0 if self.ok else 1


def main(runner: Callable[[Args], Proof], description: str) -> None:
    """Every proof's entry point: parse, run, exit non-zero on any failed check."""
    args = parse(description)
    sys.exit(runner(args).finish())
