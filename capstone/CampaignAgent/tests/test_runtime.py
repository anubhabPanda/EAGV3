"""End-to-end proof: HTTP request -> durable scoped memory -> live graph -> answer."""
from __future__ import annotations

import json

import sourcecode.routes as agent_route
from sourcecode.core.memory.embeddings import DeterministicEmbedder


def test_agent_run_uses_memory_then_expands_to_a_grounded_answer(app_client, monkeypatch):
    app_client.app.state.runtime.memory.embedder = DeterministicEmbedder(256)

    async def fake_gateway(_app, prompt: str, _system: str):
        if "evidence-readiness critic" in _system:
            return {"text": json.dumps({"ready": True, "missing": [], "reason": "complete"}),
                    "provider": "fake", "model": "critic"}
        if "decision core of a live-graph agent" in _system:
            context = json.loads(prompt)
            nodes = {node["id"]: node for node in context["graph"]["nodes"]}
            if not nodes:
                patch = {"add": [{"id": "recall", "capability": "memory_recall",
                    "arguments": {"query": context["goal"]}, "depends_on": []}],
                    "cancel": [], "finish": False, "reason": "personal question needs scoped memory"}
            else:
                patch = {"add": [{"id": "answer", "capability": "answer_with_evidence",
                    "arguments": {"query": context["goal"]}, "depends_on": ["recall"]}],
                    "cancel": [], "finish": False, "reason": "retrieved evidence is ready"}
            return {"text": json.dumps(patch), "provider": "fake", "model": "planner"}
        assert "Authorized memory evidence" in prompt
        assert "Budget is ₹75,000." in prompt
        return {"text": "Your current budget is ₹75,000. [source: chat://u/2]", "provider": "fake", "model": "fake"}

    monkeypatch.setattr(agent_route, "gateway_text_llm", fake_gateway)
    scope = {"tenant_id": "acme", "project_id": "travel", "user_id": "rohan"}
    fact = app_client.post("/v1/agent/facts", json={**scope, "text": "Budget is ₹75,000.",
                           "source_uri": "chat://u/2"})
    assert fact.status_code == 200

    response = app_client.post("/v1/agent/runs", json={**scope, "prompt": "What is my budget?"})
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Your current budget is ₹75,000. [source: chat://u/2]"
    assert [event["kind"] for event in body["events"]] == [
        "run_started", "graph_patched", "task_started", "task_succeeded", "graph_patched",
        "task_started", "task_succeeded", "graph_patched",
    ]
    assert body["graph"]["nodes"]["recall"]["state"] == "succeeded"
    assert body["graph"]["nodes"]["answer"]["state"] == "succeeded"


def test_document_index_is_semantic_and_persistent_for_the_scope(app_client):
    app_client.app.state.runtime.memory.embedder = DeterministicEmbedder(256)
    body = {"tenant_id": "acme", "project_id": "gateway", "user_id": "rohan",
            "source_uri": "file://capacity.md",
            "text": "# Capacity\nEach Gemini key has separate quota. A second key permits parallel workers."}
    indexed = app_client.post("/v1/agent/documents", json=body)
    assert indexed.status_code == 200
    assert indexed.json()["chunks"] == 1
    chunk = indexed.json()["manifest"][0]
    assert chunk["text"] == body["text"]
    assert chunk["segmentation"]["outcome"] == "below_semantic_floor"
    assert indexed.json()["provenance"]["source_sha256"]


def test_explicit_remember_promotes_a_sourced_fact_and_recall_uses_it(app_client, monkeypatch):
    app_client.app.state.runtime.memory.embedder = DeterministicEmbedder(256)

    async def fake_gateway(_app, prompt: str, _system: str):
        if "evidence-readiness critic" in _system:
            return {"text": json.dumps({"ready": True, "missing": [], "reason": "complete"}),
                    "provider": "fake", "model": "critic"}
        if "decision core of a live-graph agent" in _system:
            context = json.loads(prompt)
            nodes = {node["id"]: node for node in context["graph"]["nodes"]}
            remembering = "Remember that" in context["goal"]
            if not nodes:
                capability = "remember_explicit_fact" if remembering else "memory_recall"
                arguments = ({"text": "Mom's birthday is 15 May 2026."} if remembering
                             else {"query": context["goal"]})
                patch = {"add": [{"id": "remember" if remembering else "recall",
                    "capability": capability, "arguments": arguments, "depends_on": []}],
                    "cancel": [], "finish": False, "reason": "use durable scoped memory"}
            else:
                parent = "remember" if remembering else "recall"
                patch = {"add": [{"id": "answer", "capability": "answer_with_evidence",
                    "arguments": {"query": context["goal"]}, "depends_on": [parent]}],
                    "cancel": [], "finish": False, "reason": "memory outcome landed"}
            return {"text": json.dumps(patch), "provider": "fake", "model": "planner"}
        if "When is mom's birthday?" in prompt:
            assert "15 May 2026" in prompt
            return {"text": "You told me it is 15 May 2026. [source: chat://birthday/1]",
                    "provider": "fake", "model": "fake"}
        return {"text": "Remembered.", "provider": "fake", "model": "fake"}

    monkeypatch.setattr(agent_route, "gateway_text_llm", fake_gateway)
    scope = {"tenant_id": "acme", "project_id": "family", "user_id": "rohan"}
    first = app_client.post("/v1/agent/runs", json={**scope,
        "prompt": "My mom's birthday is 15 May 2026. Remember that.",
        "allowed_side_effects": ["remember_explicit_fact"]})
    assert first.status_code == 200
    assert first.json()["graph"]["nodes"]["remember"]["state"] == "succeeded"

    second = app_client.post("/v1/agent/runs", json={**scope, "prompt": "When is mom's birthday?"})
    assert second.json()["answer"].startswith("You told me it is 15 May 2026")
    hits = second.json()["graph"]["nodes"]["recall"]["result"]["hits"]
    assert any(hit["kind"] == "fact" and "15 May 2026" in hit["text"] for hit in hits)


def test_http_resume_replays_persisted_run_context(app_client, monkeypatch):
    app_client.app.state.runtime.memory.embedder = DeterministicEmbedder(128)

    async def fake_gateway(_app, prompt: str, _system: str):
        if "evidence-readiness critic" in _system:
            return {"text": json.dumps({"ready": True, "missing": [], "reason": "complete"}),
                    "provider": "gemini_2", "model": "critic"}
        if "decision core of a live-graph agent" in _system:
            context = json.loads(prompt)
            return {"text": json.dumps({"add": [{"id": "answer", "capability": "answer_with_evidence",
                "arguments": {"query": context["goal"]}, "depends_on": []}], "cancel": [],
                "finish": False, "reason": "no external evidence is required"}),
                "provider": "gemini_2", "model": "fake-gemini"}
        return {"text": "resumed answer", "provider": "gemini_2", "model": "fake-gemini"}

    monkeypatch.setattr(agent_route, "gateway_text_llm", fake_gateway)
    runtime = app_client.app.state.runtime
    run_id = "recover-http"
    runtime.graph.start(run_id, context={"prompt": "What is my budget?", "scope": {
        "tenant_id": "t", "project_id": "p", "user_id": "u", "agent_id": None, "run_id": None},
        "source_uri": "api://agent/runs", "source_author": "u", "inbound_id": None})

    response = app_client.post(f"/v1/agent/runs/{run_id}/resume")
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "resumed answer"
    assert body["trace"]["agents"]["answer"]["provider"] == "gemini_2"
