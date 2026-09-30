"""The headline capability, end to end over HTTP: a run created WITH a budget.

Every test drives the real runtime, the real live graph and the real controller;
only the gateway transport is faked, so token counts are deterministic and the
arithmetic is checkable. Nothing here names a task domain: the prompt is a test
parameter, exactly as the proof harness takes it on the command line.
"""

from __future__ import annotations

import json

import pytest

from sourcecode.core.memory.embeddings import DeterministicEmbedder
from sourcecode.economics import EconomicsConfig
from sourcecode.telemetry import export_run


class FakeGateway:
    """A gateway transport that reports usage the way a real provider does.

    Input tokens scale with the prompt it was actually given and output is capped
    by the ``max_tokens`` the tier asked for, because that is the behaviour the
    controller's admission arithmetic relies on.
    """

    def __init__(self, *, wanted_output: int = 5000) -> None:
        self.wanted_output = wanted_output
        self.calls: list[dict] = []

    async def chat(self, *, prompt, system, request=None):
        request = dict(request or {})
        self.calls.append(request)
        ceiling = int(request.get("max_tokens") or self.wanted_output)
        if "evidence-readiness critic" in system:
            text = json.dumps({"ready": True, "missing": [], "reason": "complete"})
            used_output = min(80, ceiling)
        elif "decision core of a live-graph agent" in system:
            context = json.loads(prompt)
            text = json.dumps({"add": [{"id": "answer", "capability": "answer_with_evidence",
                "arguments": {"query": context["goal"]}, "depends_on": []}], "cancel": [],
                "finish": False, "reason": "the goal needs no external capability"})
            used_output = min(120, ceiling)
        else:
            text = "a grounded answer"
            used_output = min(self.wanted_output, ceiling)
        return {"text": text, "provider": "prov_1",
                "model": request.get("model", "unknown"),
                "input_tokens": len(prompt or "") // 4 + len(system or "") // 4,
                "output_tokens": used_output,
                "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0, "latency_ms": 12}

    async def health(self):
        return {"ok": True}

    async def close(self):
        return None


@pytest.fixture
def budgeted_client(app_client):
    app_client.app.state.runtime.memory.embedder = DeterministicEmbedder(128)
    app_client.app.state.gateway = FakeGateway()
    return app_client


SCOPE = {"tenant_id": "acme", "project_id": "proofs", "user_id": "reviewer"}
# The task is a parameter, never a fixture of the code under test.
TASK = "Work out what the attached material implies and report it."


def run_with_budget(client, *, budget: float, task: str = TASK, **extra):
    response = client.post("/v1/agent/runs", json={**SCOPE, "prompt": task, "budget": budget, **extra})
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# the ceiling holds
# --------------------------------------------------------------------------- #

def test_a_budgeted_run_reports_its_ledger(budgeted_client):
    body = run_with_budget(budgeted_client, budget=0.05)
    budget = body["budget"]
    assert budget is not None
    assert budget["total"] == 0.05
    assert budget["spent"] <= budget["total"]
    assert budget["calls"] >= 1
    assert budget["currency"] == "USD"
    # Cost attributes to the memory scope by default: the S13 scope, now priced.
    assert budget["principal"] == "acme/proofs/reviewer"


def test_an_explicit_principal_overrides_the_scope(budgeted_client):
    body = run_with_budget(budgeted_client, budget=0.05, principal="tenant-9/team-a")
    assert body["principal"] == "tenant-9/team-a"
    assert body["budget"]["principal"] == "tenant-9/team-a"


def test_spend_never_crosses_the_ceiling_however_small(budgeted_client):
    for ceiling in (0.05, 0.005, 0.0005, 0.00005):
        body = run_with_budget(budgeted_client, budget=ceiling)
        assert body["budget"]["spent"] <= ceiling, (ceiling, body["budget"]["spent"])


def test_a_ceiling_too_small_for_any_call_refuses_rather_than_overspending(budgeted_client):
    body = run_with_budget(budgeted_client, budget=0.0000001)
    budget = body["budget"]
    assert budget["calls"] == 0
    assert budget["spent"] == 0.0
    assert budget["refusals"] >= 1
    # The refusal is a visible planning failure, not a silent truncation.
    assert body["status"] == "failed"
    assert any(event["kind"] == "graph_patched" and event["payload"]["finish"]
               and "planner call failed visibly" in event["payload"]["reason"] for event in body["events"])


def test_no_call_is_unmetered(budgeted_client):
    body = run_with_budget(budgeted_client, budget=0.05)
    transport_calls = len(budgeted_client.app.state.gateway.calls)
    assert transport_calls == body["budget"]["calls"] > 0


def test_every_charge_names_a_node_a_role_and_a_tier(budgeted_client):
    body = run_with_budget(budgeted_client, budget=0.05)
    for charge in body["budget"]["charges"]:
        assert charge["node_id"] and charge["role"] and charge["tier"]
        assert charge["cost"] > 0
        assert charge["input_tokens"] > 0


# --------------------------------------------------------------------------- #
# nodes declare tiers; the planner allocates
# --------------------------------------------------------------------------- #

def test_every_node_declares_the_tier_its_role_needs(budgeted_client):
    body = run_with_budget(budgeted_client, budget=0.05)
    config = EconomicsConfig.load()
    for node_id, node in body["graph"]["nodes"].items():
        declared = node["metadata"].get("tier")
        assert declared in config.ladder.names, (node_id, declared)
        assert declared == config.ladder.for_role(node["metadata"].get("agent") or node["skill"]).name


def test_the_tier_reaches_the_gateway_as_request_fields(budgeted_client):
    run_with_budget(budgeted_client, budget=0.05)
    config = EconomicsConfig.load()
    models = {config.ladder.tier(name).request.get("model") for name in config.ladder.names}
    for request in budgeted_client.app.state.gateway.calls:
        assert request.get("model") in models
        assert request.get("max_tokens")


def test_the_planner_reallocates_across_the_frontier_every_round(budgeted_client):
    body = run_with_budget(budgeted_client, budget=0.05)
    allocations = body["allocations"]
    assert allocations, "a budgeted run must record its allocation rounds"
    for record in allocations:
        assert set(record) >= {"trigger_event", "frontier", "per_node", "remaining"}
        # The reserve is held back: the frontier never claims the whole remainder.
        claimed = sum(record["per_node"].values())
        assert claimed <= body["budget"]["total"] + 1e-12


def test_an_unbudgeted_run_is_unchanged(app_client, monkeypatch):
    """Economics is additive. Omit the budget and nothing about the run changes."""
    import sourcecode.routes as agent_route

    app_client.app.state.runtime.memory.embedder = DeterministicEmbedder(128)

    async def fake(_app, prompt, _system):
        if "evidence-readiness critic" in _system:
            return {"text": json.dumps({"ready": True, "missing": [], "reason": "complete"}),
                    "provider": "fake", "model": "critic"}
        if "decision core of a live-graph agent" in _system:
            context = json.loads(prompt)
            return {"text": json.dumps({"add": [{"id": "answer", "capability": "answer_with_evidence",
                "arguments": {"query": context["goal"]}, "depends_on": []}], "cancel": [],
                "finish": False, "reason": "answer directly"}), "provider": "fake", "model": "planner"}
        return {"text": "plain answer", "provider": "fake", "model": "fake"}

    monkeypatch.setattr(agent_route, "gateway_text_llm", fake)
    body = app_client.post("/v1/agent/runs", json={**SCOPE, "prompt": TASK}).json()
    assert body["budget"] is None
    assert body["economics"] is None
    assert body["answer"] == "plain answer"


# --------------------------------------------------------------------------- #
# pressure: downgrade, then refuse
# --------------------------------------------------------------------------- #

def _tight_ceiling(config: EconomicsConfig, *, fits: str, denies: str) -> float:
    """A run ceiling whose per-node allowance covers ``fits`` but not ``denies``.

    Derived from the configured ladder rather than written down, so editing
    tiers.yaml changes the number instead of breaking the test.
    """
    policy = config.policy()
    allowance = (policy.project(config.ladder.tier(fits)) + policy.project(config.ladder.tier(denies))) / 2
    return allowance / max(1.0 - config.thresholds.reserve_fraction, 1e-9)


def test_a_tight_allowance_downgrades_the_tier_a_node_asked_for(budgeted_client):
    """The downgrade claim, read out of the ledger rather than off a log line.

    The terminal node's role asks for the top rung. Given an allowance that cannot
    cover it but can cover the rung below, the controller charges the cheaper tier
    and says so.
    """
    config = EconomicsConfig.load()
    top = config.ladder.most_capable.name
    below = config.ladder.downgrade(config.ladder.most_capable).name
    body = run_with_budget(budgeted_client, budget=_tight_ceiling(config, fits=below, denies=top))

    charges = body["budget"]["charges"]
    assert charges, "the run must still have made a call"
    downgraded = [c for c in charges if c["decision"] in ("downgrade", "branch")]
    assert downgraded, [c["decision"] for c in charges]
    for charge in downgraded:
        assert config.ladder.tier(charge["tier"]).rank < config.ladder.tier(charge["requested_tier"]).rank
    assert body["budget"]["spent"] <= body["budget"]["total"]


def test_a_tight_ceiling_never_buys_more_than_the_ceiling(budgeted_client):
    config = EconomicsConfig.load()
    cheapest = config.ladder.cheapest.name
    ceiling = _tight_ceiling(config, fits=cheapest, denies=config.ladder.names[1])
    body = run_with_budget(budgeted_client, budget=ceiling)
    budget = body["budget"]
    assert budget["spent"] <= ceiling
    assert budget["calls"] <= config.thresholds.max_calls_per_run
    # Whatever the graph did, it did it at the cheapest rung it could reach.
    assert all(charge["tier"] == cheapest for charge in budget["charges"]), budget["charges"]


# --------------------------------------------------------------------------- #
# the journal is the single record; telemetry is its third consumer
# --------------------------------------------------------------------------- #

def test_the_journal_carries_the_meter(budgeted_client):
    body = run_with_budget(budgeted_client, budget=0.05)
    metered = [event for event in body["events"] if (event["payload"] or {}).get("metered_calls")]
    assert metered, "an admitted call must be recorded in the durable journal"
    total = sum(call["cost"] for event in metered for call in event["payload"]["metered_calls"])
    assert total == pytest.approx(body["budget"]["spent"])


def test_the_same_journal_exports_as_otel_spans(budgeted_client):
    body = run_with_budget(budgeted_client, budget=0.05)
    export = export_run(body, budget=body["budget"])
    totals = export.totals()
    assert totals["provider_calls"] == body["budget"]["calls"]
    assert totals["cost"] == pytest.approx(body["budget"]["spent"])
    assert totals["by_kind"]["run"] == 1
    assert totals["by_kind"]["provider_call"] == body["budget"]["calls"]


def test_the_trace_route_serves_the_span_tree(budgeted_client):
    body = run_with_budget(budgeted_client, budget=0.05)
    response = budgeted_client.get(f"/v1/agent/runs/{body['run_id']}/trace")
    assert response.status_code == 200
    trace = response.json()
    assert trace["exported_over_the_wire"] is False  # no collector needed
    assert trace["capture_content"] is False  # PII off by default
    assert trace["totals"]["provider_calls"] == body["budget"]["calls"]
    kinds = {span["kind"] for span in trace["spans"]}
    assert {"run", "agent_loop", "plan", "node", "provider_call"} <= kinds


def test_the_trace_route_404s_for_an_unknown_run(budgeted_client):
    assert budgeted_client.get("/v1/agent/runs/no-such-run/trace").status_code == 404
