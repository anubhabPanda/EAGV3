"""p4's backend round trip, tested without a backend.

p4 used to claim "a real trace lands in Jaeger" while only ever reading the spans it
had just built in memory — which proves an exporter was constructed, not that
anything arrived. The fix is a round trip: fetch the trace back out of the query API
by id and re-derive the hierarchy, the usage attributes and the content check from
the *backend's* copy.

That logic has to be right when it runs, and it runs only when a collector is up. So
it is tested here against a recorded Jaeger `GET /api/traces/{id}` payload — the real
shape, with Jaeger's `references`/`CHILD_OF` parent encoding rather than the SDK's
`parent_span_id` — plus the two ways it can legitimately decline to check anything.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "proofs"))

from p4_trace_export import (  # noqa: E402
    CONTENT_MARKERS,
    backend_hierarchy,
    fetch_trace,
    query_base,
)


def _span(span_id, kind, parent=None, name="span", tags=None):
    """One span in Jaeger's query-API shape."""
    return {
        "spanID": span_id,
        "operationName": name,
        "startTime": 1,
        "duration": 10,
        "tags": [{"key": "s15.span.kind", "value": kind}]
        + [{"key": k, "value": v} for k, v in (tags or {}).items()],
        "references": ([{"refType": "CHILD_OF", "spanID": parent}] if parent else []),
    }


def _trace():
    """The hierarchy p4 asserts on, encoded the way Jaeger returns it."""
    return {
        "traceID": "t" * 32,
        "processes": {"p1": {"serviceName": "some-service"}},
        "spans": [
            _span("a", "run", name="run r-1"),
            _span("b", "agent_loop", parent="a"),
            _span("c", "plan", parent="b"),
            _span("d", "node", parent="b"),
            _span(
                "e",
                "provider_call",
                parent="d",
                name="chat some-model",
                tags={
                    "gen_ai.provider.name": "someprovider",
                    "gen_ai.request.model": "some-model",
                    "gen_ai.usage.input_tokens": 12,
                    "gen_ai.usage.output_tokens": 3,
                    "s15.cost": 0.0004,
                },
            ),
        ],
    }


# ── the hierarchy, read from the backend's parent encoding ──────────────────


def test_every_level_is_counted_and_every_parent_is_right():
    counts, wrong, leaks = backend_hierarchy(_trace())
    assert counts == {"run": 1, "agent_loop": 1, "plan": 1, "node": 1, "provider_call": 1}
    assert wrong == []
    assert leaks == []


def test_a_reparented_span_is_caught():
    """If the wire flattened the tree, the check must fail rather than pass."""
    trace = _trace()
    for span in trace["spans"]:
        if span["spanID"] == "e":  # the provider call, hung off the run instead of a node
            span["references"] = [{"refType": "CHILD_OF", "spanID": "a"}]
    _, wrong, _ = backend_hierarchy(trace)
    assert wrong == [("chat some-model", "provider_call", "run")]


def test_an_orphaned_span_is_caught():
    trace = _trace()
    for span in trace["spans"]:
        if span["spanID"] == "e":
            span["references"] = []
    _, wrong, _ = backend_hierarchy(trace)
    assert wrong and wrong[0][2] is None


def test_content_that_reached_the_backend_is_reported():
    """The PII check is the one that must not be able to pass by accident."""
    for marker in CONTENT_MARKERS:
        trace = _trace()
        trace["spans"][-1]["tags"].append({"key": f"gen_ai.{marker}", "value": "secret text"})
        _, _, leaks = backend_hierarchy(trace)
        assert leaks == [f"gen_ai.{marker}"], marker


def test_a_trace_with_no_spans_leaks_nothing_and_counts_nothing():
    counts, wrong, leaks = backend_hierarchy({"spans": [], "processes": {}})
    assert (counts, wrong, leaks) == ({}, [], [])


# ── deciding whether to ask at all ──────────────────────────────────────────


def test_query_url_is_derived_from_the_otlp_endpoint(monkeypatch):
    monkeypatch.delenv("S17_TRACE_QUERY_URL", raising=False)
    args = SimpleNamespace(otel_endpoint="http://collector.internal:4318/v1/traces")
    assert query_base(args) == "http://collector.internal:16686"


def test_an_explicit_query_url_wins(monkeypatch):
    monkeypatch.setenv("S17_TRACE_QUERY_URL", "http://jaeger.example:16686/")
    args = SimpleNamespace(otel_endpoint="http://somewhere-else:4318")
    assert query_base(args) == "http://jaeger.example:16686"


def test_no_endpoint_means_no_query(monkeypatch):
    monkeypatch.delenv("S17_TRACE_QUERY_URL", raising=False)
    assert query_base(SimpleNamespace(otel_endpoint=None)) is None


def test_a_grpc_endpoint_still_yields_a_ui_host(monkeypatch):
    monkeypatch.delenv("S17_TRACE_QUERY_URL", raising=False)
    assert query_base(SimpleNamespace(otel_endpoint="127.0.0.1:4317")) == "http://127.0.0.1:16686"


def test_an_unreachable_backend_reports_rather_than_raises():
    """Nothing listens on port 1, and the proof must survive that with a reason."""
    found = fetch_trace("http://127.0.0.1:1", "f" * 32, attempts=1, pause=0)
    assert found["ok"] is False
    assert found["reason"]
    assert found["query"].endswith("f" * 32)
