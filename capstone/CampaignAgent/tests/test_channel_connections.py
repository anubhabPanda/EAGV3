from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx

import conftest
import sourcecode.routes as agent_route
from sourcecode.core.live_graph import Deferred, GraphPatch, TaskSpec
from sourcecode.core.memory.embeddings import DeterministicEmbedder
from sourcecode.gateway import GatewayClient


def _channel_message(**changes):
    body = {
        "channel": "telegram",
        "channel_user_id": "42",
        "user_handle": "rohan",
        "text": "Summarise what I asked in one sentence.",
        "attachments": [],
        "voice_audio_ref": None,
        "thread_id": "topic-7",
        "trust_level": "owner_paired",
        "arrived_at": datetime.now(UTC).isoformat(),
        "metadata": {"message_id": "tg-100"},
    }
    body.update(changes)
    return body


def test_channel_message_runs_the_real_graph_records_event_and_deduplicates(
    app_client, monkeypatch
):
    monkeypatch.setenv("S17_CHANNEL_BRIDGE_TOKEN", "shared")
    app_client.app.state.runtime.memory.embedder = DeterministicEmbedder(128)

    async def fake_gateway(_app, prompt: str, system: str):
        if "evidence-readiness critic" in system:
            return {"text": json.dumps({"ready": True, "missing": [], "reason": "direct request"}),
                    "provider": "fake", "model": "critic"}
        if "decision core of a live-graph agent" in system:
            context = json.loads(prompt)
            return {"text": json.dumps({
                "add": [{"id": "answer", "capability": "answer_with_evidence",
                         "arguments": {"query": context["goal"]}, "depends_on": []}],
                "cancel": [], "finish": False, "reason": "answer the addressed message",
            }), "provider": "fake", "model": "planner"}
        return {"text": "You asked me to summarise your request.",
                "provider": "fake", "model": "answer"}

    monkeypatch.setattr(agent_route, "gateway_text_llm", fake_gateway)
    headers = {"Authorization": "Bearer shared"}
    first = app_client.post("/v1/agent/channel-messages", headers=headers, json=_channel_message())
    replay = app_client.post("/v1/agent/channel-messages", headers=headers, json=_channel_message())

    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert first.json()["text"] == "You asked me to summarise your request."
    assert first.json()["thread_id"] == "topic-7"
    events = app_client.get("/v1/agent/events").json()["events"]
    assert len(events) == 1
    assert events[0]["event"]["source"] == "glc.channel.telegram"
    assert events[0]["decisions"][0]["run_status"] == "completed"


def test_channel_bridge_requires_a_shared_secret(app_client, monkeypatch):
    monkeypatch.setenv("S17_CHANNEL_BRIDGE_TOKEN", "shared")
    denied = app_client.post("/v1/agent/channel-messages", json=_channel_message())
    assert denied.status_code == 401


def test_untrusted_channel_sender_never_inherits_configured_side_effects(app_client, monkeypatch):
    monkeypatch.setenv("S17_CHANNEL_BRIDGE_TOKEN", "shared")
    monkeypatch.setenv("S17_CHANNEL_ALLOWED_SIDE_EFFECTS", "write_file")
    app_client.app.state.runtime.memory.embedder = DeterministicEmbedder(128)

    async def fake_gateway(_app, prompt: str, system: str):
        if "decision core of a live-graph agent" in system:
            return {"text": json.dumps({"add": [{"id": "write", "capability": "write_file",
                    "arguments": {"path": "forbidden.md", "content": "no"}, "depends_on": []}],
                    "cancel": [], "finish": False, "reason": "try a mutation"}),
                    "provider": "fake", "model": "planner"}
        return {"text": "unused", "provider": "fake", "model": "fake"}

    monkeypatch.setattr(agent_route, "gateway_text_llm", fake_gateway)
    response = app_client.post(
        "/v1/agent/channel-messages",
        headers={"Authorization": "Bearer shared"},
        json=_channel_message(trust_level="untrusted", metadata={"message_id": "untrusted-1"}),
    )
    assert response.status_code == 200
    run_id = response.json()["text"].rsplit(" ", 1)[-1]
    journal = app_client.get(f"/v1/agent/runs/{run_id}").json()
    assert journal["nodes"] == {}
    assert "lacks explicit run authority" in journal["events"][-1]["payload"]["reason"]


async def test_gateway_discovers_and_sends_without_a_channel_name_table(monkeypatch):
    requests = []

    async def gateway(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path, request.headers.get("authorization")))
        if request.method == "GET":
            return httpx.Response(200, json={"channels": [{"name": "future_adapter", "connected": True}]})
        return httpx.Response(200, json={"accepted": True, "channel": "future_adapter",
                                         "adapter_result": {"id": "out-1"}})

    monkeypatch.setenv("S17_CHANNEL_BRIDGE_TOKEN", "shared")
    http = httpx.AsyncClient(transport=httpx.MockTransport(gateway), base_url="http://glc")
    client = GatewayClient("http://glc", client=http)
    assert await client.channels() == [{"name": "future_adapter", "connected": True}]
    receipt = await client.send_channel(
        channel="future_adapter", recipient_id="destination", text="hello"
    )
    assert receipt["adapter_result"]["id"] == "out-1"
    assert requests == [
        ("GET", "/v1/channels", None),
        ("POST", "/v1/channels/future_adapter/send", "Bearer shared"),
    ]
    await http.aclose()


def test_a_reply_in_the_same_channel_thread_resumes_a_waiting_approval(app_client, monkeypatch):
    monkeypatch.setenv("S17_CHANNEL_BRIDGE_TOKEN", "shared")
    monkeypatch.setenv("S17_CHANNEL_ALLOWED_SIDE_EFFECTS", "request_approval")
    app_client.app.state.runtime.memory.embedder = DeterministicEmbedder(128)

    async def fake_gateway(_app, prompt: str, system: str):
        if "evidence-readiness critic" in system:
            return {"text": json.dumps({"ready": True, "missing": [], "reason": "enough"}),
                    "provider": "fake", "model": "critic"}
        if "decision core of a live-graph agent" in system:
            context = json.loads(prompt)
            nodes = context["graph"]["nodes"]
            if not nodes:
                patch = {"add": [{"id": "approve", "capability": "request_approval",
                         "arguments": {"question": "Send the final report?", "choices": ["yes", "no"]},
                         "depends_on": []}], "cancel": [], "finish": False,
                         "reason": "sending needs approval"}
            else:
                patch = {"add": [{"id": "answer", "capability": "answer_with_evidence",
                         "arguments": {"query": context["goal"]}, "depends_on": ["approve"]}],
                         "cancel": [], "finish": False, "reason": "approval arrived"}
            return {"text": json.dumps(patch), "provider": "fake", "model": "planner"}
        return {"text": "Approved; the graph resumed and completed.",
                "provider": "fake", "model": "answer"}

    monkeypatch.setattr(agent_route, "gateway_text_llm", fake_gateway)
    headers = {"Authorization": "Bearer shared"}
    first = app_client.post("/v1/agent/channel-messages", headers=headers,
                            json=_channel_message(metadata={"message_id": "approval-1"}))
    assert first.status_code == 200
    assert first.json()["text"] == "Approval needed: Send the final report? Choices: yes, no"

    second = app_client.post("/v1/agent/channel-messages", headers=headers,
                             json=_channel_message(text="yes", metadata={"message_id": "approval-2"}))
    assert second.status_code == 200
    assert second.json()["text"] == "Approved; the graph resumed and completed."
    events = app_client.get("/v1/agent/events").json()["events"]
    assert events[-1]["decisions"][0]["subscription_id"] == "channel-approval"
    run_id = events[-1]["decisions"][0]["run_id"]
    journal = app_client.get(f"/v1/agent/runs/{run_id}").json()["events"]
    assert any(event["kind"] == "external_event_received" for event in journal)


def test_job_callback_resumes_and_pushes_final_answer_to_originating_channel(app_client, monkeypatch):
    monkeypatch.setenv("S17_CHANNEL_BRIDGE_TOKEN", "shared")
    app_client.app.state.runtime.memory.embedder = DeterministicEmbedder(128)
    runtime = app_client.app.state.runtime
    origin = _channel_message(metadata={"message_id": "job-origin"})
    run_id = "channel-job-proof"
    runtime.graph.start(run_id, context={
        "prompt": origin["text"],
        "scope": {"tenant_id": "local", "project_id": "channel:telegram",
                  "user_id": "telegram:42", "agent_id": "s17-channel-agent", "run_id": None},
        "source_uri": "channel://telegram/job-origin", "source_author": "rohan",
        "inbound_id": "not-this-run", "respond_as": "text", "allowed_side_effects": ["launch_job"],
        "initial_evidence": {"channel_message": origin},
    })
    runtime.graph.apply_patch(run_id, GraphPatch(
        add=(TaskSpec("remote", "launch_job", {"endpoint": "https://worker.example/jobs",
                                                "task": "check the build"}),),
        reason="launch remote checker"), trigger_event=1)
    runtime.graph.mark_running(run_id, [TaskSpec("remote", "launch_job")])
    runtime.graph.record_waiting(run_id, "remote", Deferred("job-77", "job.completed").as_wait())

    async def fake_gateway(_app, prompt: str, system: str):
        if "evidence-readiness critic" in system:
            return {"text": json.dumps({"ready": True, "missing": [], "reason": "job completed"}),
                    "provider": "fake", "model": "critic"}
        if "decision core of a live-graph agent" in system:
            context = json.loads(prompt)
            return {"text": json.dumps({"add": [{"id": "answer",
                    "capability": "answer_with_evidence", "arguments": {"query": context["goal"]},
                    "depends_on": ["remote"]}], "cancel": [], "finish": False,
                    "reason": "use the callback result"}), "provider": "fake", "model": "planner"}
        return {"text": "The remote build completed successfully.",
                "provider": "fake", "model": "answer"}

    monkeypatch.setattr(agent_route, "gateway_text_llm", fake_gateway)
    app_client.app.state.gateway.send_channel = AsyncMock(return_value={"accepted": True, "id": "sent-1"})
    # The remote job service holds the completion token, not the control token:
    # it may finish work it was given without being able to write subscriptions.
    response = app_client.post("/v1/agent/completions", json={
        "handle": "job-77", "event_type": "job.completed", "success": True,
        "payload": {"status": "passed", "url": "https://ci.example/run/77"},
    }, headers={"Authorization": f"Bearer {conftest.COMPLETION_TOKEN}"})
    assert response.status_code == 200
    body = response.json()
    assert body["run"]["answer"] == "The remote build completed successfully."
    assert body["channel_delivery"] == {"accepted": True, "id": "sent-1"}
    app_client.app.state.gateway.send_channel.assert_awaited_once_with(
        channel="telegram", recipient_id="42", text="The remote build completed successfully.",
        thread_id="topic-7", voice_audio_ref=None,
    )


def test_general_planner_can_discover_and_use_a_future_channel_adapter(app_client, monkeypatch):
    app_client.app.state.runtime.memory.embedder = DeterministicEmbedder(128)
    app_client.app.state.gateway.channels = AsyncMock(
        return_value=[{"name": "future_adapter", "connected": True}]
    )
    app_client.app.state.gateway.send_channel = AsyncMock(
        return_value={"accepted": True, "adapter_result": {"id": "future-1"}}
    )

    async def fake_gateway(_app, prompt: str, system: str):
        if "evidence-readiness critic" in system:
            return {"text": json.dumps({"ready": True, "missing": [], "reason": "receipt available"}),
                    "provider": "fake", "model": "critic"}
        if "decision core of a live-graph agent" in system:
            context = json.loads(prompt)
            nodes = {node["id"]: node for node in context["graph"]["nodes"]}
            if not nodes:
                patch = {"add": [{"id": "channels", "capability": "list_channels",
                                   "arguments": {}, "depends_on": []}],
                         "cancel": [], "finish": False, "reason": "discover, do not assume"}
            elif "send" not in nodes:
                patch = {"add": [{"id": "send", "capability": "send_channel_message",
                    "arguments": {"channel": "future_adapter", "recipient_id": "destination",
                                  "text": "The build passed."}, "depends_on": ["channels"]}],
                    "cancel": [], "finish": False, "reason": "use discovered adapter"}
            else:
                patch = {"add": [{"id": "answer", "capability": "answer_with_evidence",
                    "arguments": {"query": context["goal"]}, "depends_on": ["send"]}],
                    "cancel": [], "finish": False, "reason": "report the real receipt"}
            return {"text": json.dumps(patch), "provider": "fake", "model": "planner"}
        return {"text": "Sent through the discovered adapter; receipt future-1.",
                "provider": "fake", "model": "answer"}

    monkeypatch.setattr(agent_route, "gateway_text_llm", fake_gateway)
    response = app_client.post("/v1/agent/runs", json={
        "tenant_id": "course", "user_id": "student", "prompt":
        "Discover whether future_adapter exists, then send 'The build passed.' to destination.",
        "allowed_side_effects": ["send_channel_message"],
    })
    assert response.status_code == 200
    body = response.json()
    assert [body["graph"]["nodes"][name]["skill"] for name in ("channels", "send", "answer")] == [
        "list_channels", "send_channel_message", "answer_with_evidence",
    ]
    app_client.app.state.gateway.send_channel.assert_awaited_once_with(
        channel="future_adapter", recipient_id="destination", text="The build passed.",
        thread_id=None, voice_audio_ref=None,
    )
