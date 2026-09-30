"""Journal -> OTel spans: the hierarchy, the GenAI attributes, and PII defaults.

Hermetic. The span tree is built from a journal dict and recorded through a local
TracerProvider whose only exporter is in memory, so these tests assert real
SDK-produced spans with no collector running anywhere.
"""

from __future__ import annotations

import pytest

from sourcecode.telemetry import build_span_tree, export_run
from sourcecode.telemetry.spans import (
    COST,
    GEN_AI_INPUT_MESSAGES,
    GEN_AI_INPUT_TOKENS,
    GEN_AI_OPERATION,
    GEN_AI_OUTPUT_MESSAGES,
    GEN_AI_OUTPUT_TOKENS,
    GEN_AI_PROVIDER,
    GEN_AI_REQUEST_MODEL,
    SPAN_KIND,
    build_tracer_provider,
)


def meter(node_id: str, *, cost: float, model: str = "m-1", started_at: float = 1_800_000_000.0) -> dict:
    """One metered-call record, in the shape the controller writes."""
    return {
        "sequence": 1, "node_id": node_id, "role": node_id, "tier": "standard",
        "provider": "prov_1", "model": model, "requested_model": model,
        "input_tokens": 1200, "output_tokens": 300, "cache_read_tokens": 0,
        "cache_write_tokens": 0, "cost": cost, "projected_cost": cost,
        "latency_ms": 42.0, "started_at": started_at, "decision": "proceed",
        "requested_tier": "standard", "reasoning": "low",
        "budget_remaining": 0.5, "budget_pressure": 0.1,
    }


@pytest.fixture
def journal() -> dict:
    """A two-node run: one planning round each, one provider call per node."""
    return {
        "run_id": "run-abc",
        "finished": True,
        "nodes": {
            "look": {"id": "look", "skill": "researcher", "state": "succeeded",
                     "metadata": {"agent": "researcher", "tier": "economy"}, "input": {}, "result": {}},
            "say": {"id": "say", "skill": "answer_with_evidence", "state": "succeeded",
                    "metadata": {"tier": "frontier"}, "input": {}, "result": {}},
        },
        "edges": (("look", "say"),),
        "events": [
            {"sequence": 1, "kind": "run_started", "node_id": None, "payload": {}},
            {"sequence": 2, "kind": "graph_patched", "node_id": None,
             "payload": {"trigger_event": 1, "reason": "first frontier", "add": ["look"], "finish": False}},
            {"sequence": 3, "kind": "task_started", "node_id": "look",
             "payload": {"skill": "researcher", "agent": "researcher"}},
            {"sequence": 4, "kind": "task_succeeded", "node_id": "look",
             "payload": {"text": "found", "metered_calls": [meter("look", cost=0.001)],
                         "budget_decisions": [{"action": "proceed", "tier": "economy",
                                               "requested_tier": "economy", "reason": "fits",
                                               "projected_cost": 0.001}]}},
            {"sequence": 5, "kind": "graph_patched", "node_id": None,
             "payload": {"trigger_event": 4, "reason": "evidence landed", "add": ["say"], "finish": False}},
            {"sequence": 6, "kind": "task_started", "node_id": "say",
             "payload": {"skill": "answer_with_evidence", "agent": "answer_with_evidence"}},
            {"sequence": 7, "kind": "task_succeeded", "node_id": "say",
             "payload": {"answer": "here", "metered_calls": [meter("say", cost=0.002, model="m-2")]}},
            {"sequence": 8, "kind": "graph_patched", "node_id": None,
             "payload": {"trigger_event": 7, "reason": "grounded answer produced", "add": [], "finish": True}},
        ],
    }


# --------------------------------------------------------------------------- #
# the hierarchy
# --------------------------------------------------------------------------- #

def test_the_tree_is_run_loop_plan_node_call(journal):
    tree = build_span_tree(journal)
    assert tree.kind == "run"
    loops = [child for child in tree.children if child.kind == "agent_loop"]
    assert len(loops) == 3  # one per graph_patched
    plans = [child for loop in loops for child in loop.children if child.kind == "plan"]
    assert len(plans) == 3
    nodes = [child for loop in loops for child in loop.children if child.kind == "node"]
    assert {node.attributes["s15.node.id"] for node in nodes} == {"look", "say"}
    calls = [child for node in nodes for child in node.children if child.kind == "provider_call"]
    assert len(calls) == 2


def test_a_node_hangs_off_the_round_that_planned_it(journal):
    tree = build_span_tree(journal)
    round_one = tree.children[0]
    assert [child.attributes.get("s15.node.id") for child in round_one.children if child.kind == "node"] == ["look"]
    round_two = tree.children[1]
    assert [child.attributes.get("s15.node.id") for child in round_two.children if child.kind == "node"] == ["say"]


def test_the_journal_is_the_only_input_no_parallel_event_system(journal):
    """Delete the materialised nodes and the trace still builds from the tape."""
    tape_only = {**journal, "nodes": {}}
    tree = build_span_tree(tape_only)
    calls = [span for span in tree.walk() if span.kind == "provider_call"]
    assert len(calls) == 2


# --------------------------------------------------------------------------- #
# GenAI semantic-convention attributes + cost
# --------------------------------------------------------------------------- #

def test_provider_call_spans_carry_the_genai_attributes_and_cost(journal):
    export = export_run(journal, budget={"currency": "USD", "total": 1.0, "spent": 0.003,
                                         "remaining": 0.997, "principal": "t/p"})
    calls = export.provider_call_spans()
    assert len(calls) == 2
    for span in calls:
        attributes = dict(span.attributes)
        assert attributes[GEN_AI_OPERATION] == "chat"
        assert attributes[GEN_AI_PROVIDER] == "prov_1"
        assert attributes[GEN_AI_REQUEST_MODEL] in {"m-1", "m-2"}
        assert attributes[GEN_AI_INPUT_TOKENS] == 1200
        assert attributes[GEN_AI_OUTPUT_TOKENS] == 300
        assert attributes[COST] > 0
        assert attributes["s15.currency"] == "USD"


def test_totals_add_up_to_the_run(journal):
    export = export_run(journal)
    totals = export.totals()
    assert totals["provider_calls"] == 2
    assert totals["input_tokens"] == 2400
    assert totals["output_tokens"] == 600
    assert totals["cost"] == pytest.approx(0.003)
    assert len(totals["trace_ids"]) == 1  # one run, one trace


def test_node_spans_are_execute_tool_and_carry_their_tier(journal):
    export = export_run(journal)
    nodes = [s for s in export.spans if dict(s.attributes).get(SPAN_KIND) == "node"]
    assert {dict(s.attributes)["gen_ai.operation.name"] for s in nodes} == {"execute_tool"}
    tiers = {dict(s.attributes)["s15.node.id"]: dict(s.attributes).get("s15.tier") for s in nodes}
    assert tiers == {"look": "economy", "say": "frontier"}


def test_a_failed_node_becomes_an_error_span(journal):
    journal["events"][6] = {"sequence": 7, "kind": "task_failed", "node_id": "say",
                            "payload": {"error": "BudgetRefused: no room"}}
    export = export_run(journal)
    failed = [s for s in export.spans if dict(s.attributes).get("s15.node.id") == "say"
              and dict(s.attributes).get(SPAN_KIND) == "node"]
    assert failed and failed[0].status.status_code.name == "ERROR"
    assert "BudgetRefused" in (failed[0].status.description or "")


def test_a_refusal_appears_on_the_run_span_as_an_event(journal):
    export = export_run(journal, budget={
        "currency": "USD", "total": 0.001, "spent": 0.001, "remaining": 0.0, "refusals": 1,
        "refusal_log": [{"node_id": "say", "reason": "spend pressure 1.000 >= refuse_at 0.9",
                         "spent": 0.001, "remaining": 0.0}],
    })
    run_span = next(s for s in export.spans if dict(s.attributes).get(SPAN_KIND) == "run")
    names = [event.name for event in run_span.events]
    assert "budget.refused" in names
    assert dict(run_span.attributes)["s15.budget.refusals"] == 1


def test_budget_decisions_land_as_span_events(journal):
    export = export_run(journal)
    look = next(s for s in export.spans if dict(s.attributes).get("s15.node.id") == "look"
                and dict(s.attributes).get(SPAN_KIND) == "node")
    assert [event.name for event in look.events] == ["budget.decision"]


# --------------------------------------------------------------------------- #
# PII: content capture is OFF by default
# --------------------------------------------------------------------------- #

def test_content_capture_is_off_by_default(journal, monkeypatch):
    monkeypatch.delenv("S17_OTEL_CAPTURE_CONTENT", raising=False)
    journal["events"][3]["payload"]["metered_calls"][0].update(
        {"prompt": "a private prompt", "completion": "a private completion"})
    export = export_run(journal)
    assert export.capture_content is False
    for span in export.spans:
        attributes = dict(span.attributes)
        assert GEN_AI_INPUT_MESSAGES not in attributes
        assert GEN_AI_OUTPUT_MESSAGES not in attributes
    assert "a private prompt" not in str(export.as_dict())


def test_content_capture_is_opt_in_per_call(journal):
    journal["events"][3]["payload"]["metered_calls"][0].update(
        {"prompt": "a private prompt", "completion": "a private completion"})
    export = export_run(journal, capture_content=True)
    assert export.capture_content is True
    captured = [dict(s.attributes) for s in export.spans if GEN_AI_INPUT_MESSAGES in dict(s.attributes)]
    assert captured and captured[0][GEN_AI_INPUT_MESSAGES] == "a private prompt"


def test_the_env_switch_also_opts_in(journal, monkeypatch):
    monkeypatch.setenv("S17_OTEL_CAPTURE_CONTENT", "1")
    journal["events"][3]["payload"]["metered_calls"][0]["prompt"] = "x"
    assert export_run(journal).capture_content is True


# --------------------------------------------------------------------------- #
# the exporter is configuration, and a no-op when unset
# --------------------------------------------------------------------------- #

def test_no_endpoint_means_nothing_goes_over_the_wire(journal, monkeypatch):
    monkeypatch.delenv("S17_OTEL_EXPORTER_ENDPOINT", raising=False)
    export = export_run(journal)
    assert export.exported_over_the_wire is False
    assert export.endpoint is None
    # ...and the tree is still complete, which is what makes CI possible.
    assert export.totals()["spans"] >= 8


def test_the_endpoint_is_read_from_config(monkeypatch):
    monkeypatch.setenv("S17_OTEL_EXPORTER_ENDPOINT", "")
    provider, memory, wired = build_tracer_provider(endpoint=None)
    assert wired is False
    provider.shutdown()


def test_service_name_is_configurable(journal, monkeypatch):
    monkeypatch.setenv("S17_OTEL_SERVICE_NAME", "custom-service")
    assert export_run(journal).service_name == "custom-service"
    assert export_run(journal, service_name="explicit").service_name == "explicit"


# --------------------------------------------------------------------------- #
# span times
# --------------------------------------------------------------------------- #

def test_provider_spans_use_the_real_measured_duration(journal):
    export = export_run(journal)
    for span in export.provider_call_spans():
        # 42 ms, as the meter recorded it.
        assert (span.end_time - span.start_time) == 42 * 1_000_000


def test_parents_enclose_their_children(journal):
    tree = build_span_tree(journal)
    for span in tree.walk():
        for child in span.children:
            assert span.start_ns <= child.start_ns
            assert span.end_ns >= child.end_ns


def test_an_empty_journal_still_produces_a_run_span():
    export = export_run({"run_id": "empty", "finished": False, "nodes": {}, "edges": (), "events": []})
    assert export.totals()["spans"] == 1
    assert export.totals()["provider_calls"] == 0
