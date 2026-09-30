#!/usr/bin/env python
"""p4 — the journal exports as OpenTelemetry spans, with usage and cost per span.

Session 14 turned the durable event journal into AG-UI events. Session 15 turns
the same journal into OTel spans. Nothing new is recorded, which is the claim
worth proving: delete the materialised graph and the trace still builds from the
tape alone.

What is checked:

1. The hierarchy is ``run -> agent loop -> plan -> node -> provider call``, read
   back from the parent pointers the SDK actually produced.
2. Every provider-call span carries the GenAI semantic-convention attributes
   ``gen_ai.provider.name``, ``gen_ai.request.model``, ``gen_ai.usage.input_tokens``
   and ``gen_ai.usage.output_tokens``, plus a cost.
3. Span costs sum to exactly what the budget ledger says was spent.
4. Content capture is OFF: no prompt or completion text is anywhere in the trace.
5. It works with no collector. Give ``--otel-endpoint`` and the same spans also go
   over the wire to Jaeger or any OTLP receiver.
6. **The trace really landed.** Steps 1–5 all read the spans this process built,
   which proves the exporter was *installed*, not that anything arrived. So when a
   query API is reachable the proof reads the trace back *out of the backend* by id
   and re-checks the hierarchy, the usage attributes and the absence of content on
   the spans the backend actually stored. Nothing else in this repo can make the
   claim "a real trace lands in Jaeger" true; a round trip can.

   The query URL is ``S17_TRACE_QUERY_URL`` if set, and otherwise derived from the
   OTLP endpoint's host on Jaeger's default UI port — so pointing the exporter at a
   local Jaeger is enough, with no second flag to remember. When nothing is
   reachable the round trip is reported as *not attempted* and the proof still
   passes, because a collector is a deployment choice and not an invariant.

    python proofs/p4_trace_export.py --task "<anything>" --budget 0.02
    python proofs/p4_trace_export.py --task "<anything>" --budget 0.02 --offline
    #   with Jaeger up, the round trip happens automatically:
    python proofs/p4_trace_export.py --task "<anything>" \
        --otel-endpoint http://127.0.0.1:4318/v1/traces
    #   ... or name a query API that is somewhere else:
    S17_TRACE_QUERY_URL=http://jaeger.internal:16686 python proofs/p4_trace_export.py --task "<anything>"
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from harness import Args, Proof, main, run_task, sync, transport_for

from sourcecode.telemetry import export_run
from sourcecode.telemetry.spans import (
    COST,
    GEN_AI_INPUT_MESSAGES,
    GEN_AI_INPUT_TOKENS,
    GEN_AI_OUTPUT_MESSAGES,
    GEN_AI_OUTPUT_TOKENS,
    GEN_AI_PROVIDER,
    GEN_AI_REQUEST_MODEL,
)

REQUIRED_GENAI = (GEN_AI_PROVIDER, GEN_AI_REQUEST_MODEL, GEN_AI_INPUT_TOKENS, GEN_AI_OUTPUT_TOKENS)
EXPECTED_PARENT = {"agent_loop": "run", "plan": "agent_loop", "node": "agent_loop", "provider_call": "node"}

#: Attribute-name fragments that would mean prompt or completion text escaped into
#: the backend. Checked as substrings so a renamed convention cannot slip past.
CONTENT_MARKERS = ("input.messages", "output.messages", "prompt", "completion")

#: Jaeger's default UI/query port. Only used to guess a query URL from the OTLP
#: endpoint's host when the operator did not name one.
DEFAULT_QUERY_PORT = 16686


# --- reading the trace back out of the backend ----------------------------- #


def query_base(args: Args) -> str | None:
    """Where to ask "did it arrive?". Explicit beats derived; derived beats nothing."""
    explicit = (os.getenv("S17_TRACE_QUERY_URL") or "").strip()
    if explicit:
        return explicit.rstrip("/")
    if not args.otel_endpoint:
        return None
    host = re.sub(r"^\w+://", "", args.otel_endpoint).split("/", 1)[0].rsplit(":", 1)[0]
    return f"http://{host}:{DEFAULT_QUERY_PORT}" if host else None


def fetch_trace(base: str, trace_id: str, *, attempts: int = 12, pause: float = 1.0) -> dict:
    """Poll ``GET {base}/api/traces/{trace_id}`` until the backend has indexed it.

    Ingestion is asynchronous, so a single immediate GET would be a flaky test of a
    working system. Polling makes the check about arrival rather than about timing.
    """
    last = "no attempt made"
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(f"{base}/api/traces/{trace_id}", timeout=5) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            data = payload.get("data") or []
            if data and data[0].get("spans"):
                return {"ok": True, "trace": data[0], "query": f"{base}/api/traces/{trace_id}"}
            last = "backend answered with no spans for that id"
        except urllib.error.URLError as e:
            last = f"{type(e).__name__}: {e}"
        except Exception as e:  # pragma: no cover - any backend hiccup is just "not yet"
            last = f"{type(e).__name__}: {e}"
        time.sleep(pause)
    return {"ok": False, "reason": last, "query": f"{base}/api/traces/{trace_id}"}


def backend_hierarchy(trace: dict) -> tuple[dict[str, int], list, list]:
    """Read kinds, parent-kind pairs and content leaks from the *backend's* copy."""
    spans = trace.get("spans") or []
    tags = {s["spanID"]: {t["key"]: t.get("value") for t in (s.get("tags") or [])} for s in spans}

    def parent_of(span):
        for ref in span.get("references") or []:
            if ref.get("refType") == "CHILD_OF":
                return ref.get("spanID")
        return None

    counts: dict[str, int] = {}
    for span_id, attrs in tags.items():
        kind = str(attrs.get("s15.span.kind", "unknown"))
        counts[kind] = counts.get(kind, 0) + 1
    wrong = []
    for span in spans:
        kind = str(tags[span["spanID"]].get("s15.span.kind", ""))
        expected = EXPECTED_PARENT.get(kind)
        if expected is None:
            continue
        parent = parent_of(span)
        got = str(tags.get(parent, {}).get("s15.span.kind")) if parent else None
        if got != expected:
            wrong.append((span["operationName"], kind, got))
    leaks = sorted(
        {key for attrs in tags.values() for key in attrs if any(m in key for m in CONTENT_MARKERS)}
    )
    return counts, wrong, leaks


def run(args: Args) -> Proof:
    transport, mode, detail = transport_for(args)
    proof = Proof(name="p4_trace_export", args=args, mode=mode, mode_detail=detail)

    with tempfile.TemporaryDirectory(prefix="s15-p4-") as workspace:
        outcome = sync(run_task(args, budget=args.budget, transport=transport,
                                data_dir=Path(workspace) / "run"))

    journal = outcome.journal
    budget = outcome.budget
    export = export_run(journal, budget=budget, endpoint=args.otel_endpoint,
                        principal=args.principal)
    spans = export.as_dict()["spans"]
    by_id = {span["span_id"]: span for span in spans}
    totals = export.totals()

    proof.fact("journal events", len(journal["events"]))
    proof.fact("spans", totals["spans"])
    proof.fact("span kinds", totals["by_kind"])
    proof.fact("provider calls", totals["provider_calls"])
    proof.fact("input tokens", totals["input_tokens"])
    proof.fact("output tokens", totals["output_tokens"])
    proof.fact("span cost total", f"{totals['cost']:.8f}")
    proof.fact("ledger spent", f"{budget.get('spent', 0.0):.8f}")
    proof.fact("trace ids", totals["trace_ids"])
    proof.fact("otlp endpoint", args.otel_endpoint or "(none: spans built, nothing sent)")

    # 1. the hierarchy
    kinds = set(totals["by_kind"])
    proof.check("every level of the hierarchy is present",
                {"run", "agent_loop", "plan", "node", "provider_call"} <= kinds,
                sorted(kinds))
    wrong_parents = []
    for span in spans:
        expected = EXPECTED_PARENT.get(span["kind"])
        if expected is None:
            continue
        parent = by_id.get(span["parent_span_id"] or "")
        if not parent or parent["kind"] != expected:
            wrong_parents.append((span["name"], span["kind"], parent["kind"] if parent else None))
    proof.check("run -> agent loop -> plan -> node -> provider call",
                not wrong_parents, wrong_parents or "every parent is the expected kind")
    proof.check("one run is one trace", len(totals["trace_ids"]) == 1, totals["trace_ids"])

    # 2. GenAI attributes on every provider call
    missing = [
        (span["name"], [name for name in REQUIRED_GENAI if name not in span["attributes"]])
        for span in spans if span["kind"] == "provider_call"
        and any(name not in span["attributes"] for name in REQUIRED_GENAI)
    ]
    proof.check("gen_ai.* usage attributes on every provider call", not missing,
                missing or f"{totals['provider_calls']} spans carry all of {list(REQUIRED_GENAI)}")
    uncosted = [span["name"] for span in spans
                if span["kind"] == "provider_call" and not span["attributes"].get(COST, 0) > 0]
    proof.check("cost per provider-call span", not uncosted,
                uncosted or f"all {totals['provider_calls']} priced")

    # 3. the trace and the ledger agree
    delta = abs(totals["cost"] - budget.get("spent", 0.0))
    proof.check("span costs sum to the ledger", delta < 1e-12,
                f"delta {delta:.3e}")
    ledger_tokens = sum(c["input_tokens"] for c in budget.get("charges", []))
    proof.check("span token counts match the ledger",
                totals["input_tokens"] == ledger_tokens,
                f"{totals['input_tokens']} == {ledger_tokens}")

    # 4. PII: no content anywhere in the trace
    leaked = [span["name"] for span in spans
              if GEN_AI_INPUT_MESSAGES in span["attributes"] or GEN_AI_OUTPUT_MESSAGES in span["attributes"]]
    task_leaked = args.task in str([span["attributes"] for span in spans])
    proof.check("content capture is off by default",
                not leaked and not export.capture_content and not task_leaked,
                f"capture_content={export.capture_content}, message attrs on {len(leaked)} spans, "
                f"task text present: {task_leaked}")

    # 5. the journal alone is enough
    tape_only = export_run({**journal, "nodes": {}}, budget=budget)
    proof.check("the tape alone rebuilds the trace",
                tape_only.totals()["provider_calls"] == totals["provider_calls"],
                f"{tape_only.totals()['provider_calls']} provider calls from events only")
    proof.check("no collector is required" if not args.otel_endpoint else "spans were exported over the wire",
                export.exported_over_the_wire == bool(args.otel_endpoint),
                f"exported_over_the_wire={export.exported_over_the_wire}")

    # 6. the round trip: is it actually in the backend?
    base = query_base(args)
    trace_id = totals["trace_ids"][0] if totals["trace_ids"] else None
    proof.fact("trace query url", base or "(none: no backend to ask)")
    if not (base and trace_id and export.exported_over_the_wire):
        # Not a failure. Building the spans is the invariant; shipping them to a
        # particular backend is a deployment, and the proof must run in CI with none.
        proof.fact("backend round trip", "not attempted")
        proof.check("a real trace lands in the backend (skipped: none configured)", True,
                    f"otel_endpoint={args.otel_endpoint or None}, query={base or None}")
    else:
        found = fetch_trace(base, trace_id)
        proof.fact("backend query", found["query"])
        proof.check("a real trace lands in the backend, fetched back by id", found["ok"],
                    found.get("reason") or f"{len(found['trace']['spans'])} spans returned")
        if found["ok"]:
            trace = found["trace"]
            counts, wrong, leaks = backend_hierarchy(trace)
            services = sorted({p.get("serviceName") for p in (trace.get("processes") or {}).values()})
            proof.fact("backend spans", len(trace["spans"]))
            proof.fact("backend span kinds", counts)
            proof.fact("backend service", services)
            proof.check("the backend holds every span this process emitted",
                        len(trace["spans"]) == totals["spans"],
                        f"{len(trace['spans'])} in backend == {totals['spans']} emitted")
            proof.check("the hierarchy survives the wire (parents read from the backend)",
                        not wrong and {"run", "agent_loop", "plan", "node", "provider_call"} <= set(counts),
                        wrong or sorted(counts))
            backend_calls = [
                {t["key"]: t.get("value") for t in (s.get("tags") or [])}
                for s in trace["spans"]
                if any(t.get("key") == "s15.span.kind" and t.get("value") == "provider_call"
                       for t in (s.get("tags") or []))
            ]
            missing_backend = [
                [name for name in REQUIRED_GENAI if name not in attrs] for attrs in backend_calls
            ]
            proof.check("gen_ai.usage.* and cost are visible on the backend's spans",
                        bool(backend_calls) and not any(missing_backend)
                        and all(float(a.get(COST, 0) or 0) > 0 for a in backend_calls),
                        [{k: a.get(k) for k in (*REQUIRED_GENAI, COST)} for a in backend_calls]
                        or "no provider-call span in the backend")
            proof.check("no prompt or completion text reached the backend", not leaks,
                        leaks or f"none of {list(CONTENT_MARKERS)} appears in any backend tag")
            proof.record("backend_trace", trace)

    proof.record("budget", budget)
    proof.record("totals", totals)
    proof.record("spans", spans)
    return proof


if __name__ == "__main__":
    main(run, __doc__ or "")
