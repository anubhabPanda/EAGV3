"""Local agent-runtime endpoints."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from sourcecode.auth import require_completion, require_control
from sourcecode.core.memory import MemoryKind, MemoryScope, Principal
from sourcecode.telemetry import export_run

router = APIRouter(prefix="/v1/agent", tags=["live agent"])


async def gateway_text_llm(app, prompt: str, system: str):
    """Patchable test seam; production crosses HTTP through GatewayClient."""
    return await app.state.gateway.complete(prompt, system)


class ScopeBody(BaseModel):
    tenant_id: str
    project_id: str | None = None
    user_id: str | None = None
    agent_id: str | None = None

    def scope(self, run_id: str | None = None) -> MemoryScope:
        return MemoryScope(self.tenant_id, self.project_id, self.user_id, self.agent_id, run_id)


class RunBody(ScopeBody):
    prompt: str = Field(min_length=1, max_length=40_000)
    # How the run should answer: a plain text answer ("text", the default) or a
    # composed, validated A2UI interface ("ui"). Additive and domain-agnostic.
    respond_as: str = Field(default="text", pattern="^(text|ui)$")
    # S15: hand the run a ceiling. Omit it and the run is unbudgeted, exactly as
    # before. The principal defaults to the memory scope, so cost attributes to
    # the same tenant/project/user/agent the evidence was authorised for.
    budget: float | None = Field(default=None, gt=0)
    principal: str | None = Field(default=None, max_length=200)
    allowed_side_effects: list[str] = Field(default_factory=list, max_length=20)


class ResumeBody(BaseModel):
    run_id: str = Field(min_length=1, max_length=128)


class CompletionBody(BaseModel):
    handle: str = Field(min_length=1, max_length=500)
    event_type: str = Field(default="job.completed", min_length=1, max_length=200)
    success: bool = True
    payload: dict[str, Any] = Field(default_factory=dict)


class FactBody(ScopeBody):
    text: str = Field(min_length=1, max_length=20_000)
    source_uri: str
    source_author: str = "user"
    supersedes_id: str | None = None


class IndexBody(ScopeBody):
    text: str = Field(min_length=1, max_length=500_000)
    source_uri: str
    source_author: str = "indexer"


class SearchBody(ScopeBody):
    query: str = Field(min_length=1, max_length=20_000)
    limit: int = Field(default=5, ge=1, le=50)
    kinds: list[MemoryKind] | None = None


class ChannelMessageBody(BaseModel):
    """A dependency-free copy of GLC's stable channel envelope."""

    channel: str = Field(min_length=1, max_length=100)
    channel_user_id: str = Field(min_length=1, max_length=2_000)
    user_handle: str = Field(max_length=2_000)
    text: str | None = Field(default=None, max_length=40_000)
    attachments: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    voice_audio_ref: str | None = Field(default=None, max_length=4_000)
    thread_id: str | None = Field(default=None, max_length=2_000)
    trust_level: str = Field(pattern="^(owner_paired|user_paired|untrusted)$")
    arrived_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    def event_id(self) -> str:
        for key in ("message_id", "event_id", "update_id", "sid"):
            candidate = self.metadata.get(key)
            if isinstance(candidate, (str, int)) and str(candidate).strip():
                return str(candidate).strip()
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


def _channel_reply(body: ChannelMessageBody, result: dict[str, Any],
                   human_gates: set[str] | None = None) -> dict[str, Any]:
    if result["status"] == "completed":
        text = result.get("answer") or "Completed."
    elif result["status"] == "waiting":
        waiting = [node for node in result.get("graph", {}).get("nodes", {}).values()
                   if node.get("state") == "waiting"]
        # Which capability parks for a person is a property of the capability,
        # declared as family "human_gate", not something this route memorises.
        gates = human_gates or set()
        approvals = [node.get("wait", {}) for node in waiting
                     if node.get("skill") in gates]
        if len(approvals) == 1 and approvals[0].get("question"):
            choices = approvals[0].get("choices") or []
            suffix = f" Choices: {', '.join(choices)}" if choices else ""
            text = f"Approval needed: {approvals[0]['question']}{suffix}"
        else:
            text = f"Work started and waiting for an external result. Run: {result['run_id']}"
    else:
        text = f"I could not complete that request. Run: {result['run_id']}"
    return {
        "channel": body.channel,
        "channel_user_id": body.channel_user_id,
        "text": text,
        "attachments": [],
        "voice_audio_ref": None,
        "thread_id": body.thread_id,
    }


def _channel_origin(runtime, run_id: str) -> ChannelMessageBody | None:
    """Recover reply routing from the run checkpoint, not process memory."""
    try:
        raw = runtime.graph.context(run_id).get("initial_evidence", {}).get("channel_message")
        return ChannelMessageBody.model_validate(raw) if raw else None
    except (KeyError, ValueError):
        return None


def _waiting_channel_approval(request: Request, body: ChannelMessageBody):
    """Find one approval parked in the same provider conversation."""
    for record in reversed(request.app.state.event_store.events()):
        prior = record.get("event", {}).get("data", {})
        if (prior.get("channel") != body.channel
                or prior.get("channel_user_id") != body.channel_user_id
                or prior.get("thread_id") != body.thread_id):
            continue
        for decision in reversed(record.get("decisions", [])):
            run_id = decision.get("run_id")
            if not run_id:
                continue
            try:
                snapshot = request.app.state.runtime.graph.snapshot(run_id)
            except KeyError:
                continue
            gates = request.app.state.runtime.registry.family("human_gate")
            waits = [node.get("wait") for node in snapshot.nodes.values()
                     if node.get("state") == "waiting" and node.get("skill") in gates]
            waits = [wait for wait in waits if wait and wait.get("event_type") == "approval.received"]
            if len(waits) == 1:
                return run_id, waits[0]
    return None


async def _resume_channel_approval(request: Request, body: ChannelMessageBody):
    pending = _waiting_channel_approval(request, body)
    if pending is None:
        return None
    run_id, wait = pending
    completion = request.app.state.runtime.graph.complete_waiting(
        wait["handle"], "approval.received",
        {"response": body.text or "", "channel": body.channel,
         "channel_user_id": body.channel_user_id, "thread_id": body.thread_id},
    )
    if completion is None:
        return None
    return await request.app.state.runtime.run(
        prompt=None, scope=None,
        llm=lambda prompt, system: gateway_text_llm(request.app, prompt, system),
        source_uri=None, source_author=None, run_id=run_id, resume=True,
        transport=request.app.state.gateway,
    )


@router.post("/runs", dependencies=[Depends(require_control)])
async def run(body: RunBody, request: Request):
    runtime = request.app.state.runtime
    try:
        return await runtime.run(prompt=body.prompt, scope=body.scope(),
                                 llm=lambda prompt, system: gateway_text_llm(request.app, prompt, system),
                                 source_uri="api://agent/runs", source_author=body.user_id or "api-user",
                                 respond_as=body.respond_as, budget=body.budget, principal=body.principal,
                                 allowed_side_effects=set(body.allowed_side_effects),
                                 transport=request.app.state.gateway)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except RuntimeError as error:
        raise HTTPException(503, str(error)) from error


@router.post("/channel-messages")
async def channel_message(
    body: ChannelMessageBody,
    request: Request,
    authorization: str | None = Header(default=None),
):
    """Run any GLC channel envelope through the same S17 live graph."""
    expected = os.getenv("S17_CHANNEL_BRIDGE_TOKEN", "").strip()
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not expected:
        raise HTTPException(503, "S17_CHANNEL_BRIDGE_TOKEN is not configured")
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(401, "invalid channel bridge token")

    event_id = body.event_id()
    source = f"glc.channel.{body.channel}"
    event = {
        "id": event_id,
        "source": source,
        "type": "channel.message.received",
        "subject": body.thread_id or body.channel_user_id,
        "occurred_at": body.arrived_at.isoformat(),
        "observed_at": datetime.now(UTC).isoformat(),
        "data": body.model_dump(mode="json"),
        "traceparent": None,
    }
    from sourcecode.events import EventEnvelope

    record, fresh = request.app.state.event_store.ingest(EventEnvelope.model_validate(event))
    if not fresh:
        prior = next((item for item in record["decisions"] if isinstance(item.get("reply"), dict)), None)
        if prior and isinstance(prior.get("reply"), dict):
            return prior["reply"]

    resumed = await _resume_channel_approval(request, body)
    if resumed is not None:
        reply = _channel_reply(body, resumed, request.app.state.runtime.registry.family("human_gate"))
        request.app.state.event_store.add_decision(source, event_id, {
            "subscription_id": "channel-approval",
            "relevant": True,
            "reason": "The message answers the one approval waiting in this channel thread.",
            "goal": body.text or "",
            "run_id": resumed["run_id"],
            "run_status": resumed["status"],
            "reply": reply,
        })
        return reply

    prompt = body.text or "Respond to the attached channel message."
    initial_evidence = {"channel_message": body.model_dump(mode="json")}
    configured_authority = {
        item.strip()
        for item in os.getenv("S17_CHANNEL_ALLOWED_SIDE_EFFECTS", "").split(",")
        if item.strip()
    }
    # A public/mentioned message may be allowed to ask a question, but only a
    # gateway-verified installation owner inherits configured mutation rights.
    allowed = configured_authority if body.trust_level == "owner_paired" else set()
    try:
        principal_id = body.metadata.get("glc_principal_id")
        if not isinstance(principal_id, str) or not principal_id.strip():
            principal_id = f"{body.channel}:{body.channel_user_id}"
        result = await request.app.state.runtime.run(
            prompt=prompt,
            scope=MemoryScope(
                os.getenv("S17_CHANNEL_TENANT", "local"),
                "channels",
                principal_id,
                "s17-channel-agent",
            ),
            llm=lambda prompt, system: gateway_text_llm(request.app, prompt, system),
            source_uri=f"channel://{body.channel}/{event_id}",
            source_author=body.user_handle or body.channel_user_id,
            allowed_side_effects=allowed,
            transport=request.app.state.gateway,
            initial_evidence=initial_evidence,
        )
    except (ValueError, RuntimeError) as error:
        raise HTTPException(503, str(error)) from error

    reply = _channel_reply(body, result, request.app.state.runtime.registry.family("human_gate"))
    request.app.state.event_store.add_decision(source, event_id, {
        "subscription_id": "channel-direct",
        "relevant": True,
        "reason": "A directly addressed channel message is an explicit request.",
        "goal": prompt,
        "run_id": result["run_id"],
        "run_status": result["status"],
        "reply": reply,
    })
    return reply


@router.post("/runs/{run_id}/resume", dependencies=[Depends(require_control)])
async def resume(run_id: str, request: Request):
    runtime = request.app.state.runtime
    try:
        return await runtime.run(prompt=None, scope=None,
                                 llm=lambda prompt, system: gateway_text_llm(request.app, prompt, system),
                                 source_uri=None, source_author=None, run_id=run_id, resume=True)
    except KeyError:
        raise HTTPException(404, "run not found") from None
    except RuntimeError as error:
        raise HTTPException(503, str(error)) from error


@router.post("/completions", dependencies=[Depends(require_completion)])
async def complete_waiting_job(body: CompletionBody, request: Request):
    """Consume an idempotent completion and continue from its real outcome."""
    runtime = request.app.state.runtime
    completion = runtime.graph.complete_waiting(
        body.handle, body.event_type, body.payload, success=body.success
    )
    if completion is None:
        # The same response is safe for an unknown and an already-consumed
        # handle: callers can retry without learning internal run identifiers.
        return {"accepted": False, "duplicate_or_unknown": True}
    run_id, node_id, _ = completion
    result = await runtime.run(
        prompt=None, scope=None,
        llm=lambda prompt, system: gateway_text_llm(request.app, prompt, system),
        source_uri=None, source_author=None, run_id=run_id, resume=True,
        transport=request.app.state.gateway,
    )
    channel_delivery = None
    origin = _channel_origin(runtime, run_id)
    if origin is not None and result["status"] in {"completed", "failed"}:
        reply = _channel_reply(origin, result, request.app.state.runtime.registry.family("human_gate"))
        try:
            channel_delivery = await request.app.state.gateway.send_channel(
                channel=reply["channel"], recipient_id=reply["channel_user_id"],
                text=reply["text"], thread_id=reply["thread_id"],
                voice_audio_ref=reply["voice_audio_ref"],
            )
        except Exception as error:
            channel_delivery = {"accepted": False, "error": f"{type(error).__name__}: {error}"}
    return {"accepted": True, "run_id": run_id, "node_id": node_id,
            "run": result, "channel_delivery": channel_delivery}


@router.post("/facts")
async def fact(body: FactBody, request: Request):
    return request.app.state.runtime.remember_fact(text=body.text, scope=body.scope(), source_uri=body.source_uri,
        source_author=body.source_author, principal=Principal("gateway", "gateway"), supersedes_id=body.supersedes_id)


@router.post("/documents")
async def document(body: IndexBody, request: Request):
    return request.app.state.runtime.index_document(text=body.text, source_uri=body.source_uri,
                                                        scope=body.scope(), source_author=body.source_author)


@router.post("/memory/search")
async def memory_search(body: SearchBody, request: Request):
    hits = request.app.state.runtime.memory.recall(body.query, body.scope(),
                                                       kinds=body.kinds, limit=body.limit)
    return {"query": body.query, "hits": [{"id": hit.id, "kind": hit.kind.value,
            "text": hit.text, "sources": [source.uri for source in hit.sources],
            "metadata": hit.metadata} for hit in hits]}


def _journal(runtime, run_id: str) -> dict:
    """One run in the journal shape every consumer reads."""
    try:
        snapshot = runtime.graph.snapshot(run_id)
    except KeyError:
        raise HTTPException(404, "run not found") from None
    return {"run_id": run_id, "finished": snapshot.finished, "nodes": snapshot.nodes,
            "edges": snapshot.edges,
            "events": [{"sequence": e.sequence, "kind": e.kind, "node_id": e.node_id,
                        "payload": e.payload} for e in runtime.graph.events(run_id)]}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request):
    return _journal(request.app.state.runtime, run_id)


@router.get("/runs/{run_id}/trace")
async def get_trace(run_id: str, request: Request, endpoint: str | None = None):
    """The run's journal exported as OpenTelemetry spans.

    Same tape the UI streams as AG-UI events, read by a different consumer. With
    no exporter endpoint configured this still returns the full span tree — it
    simply sends nothing over the wire, so the route works with no collector.
    """
    export = export_run(_journal(request.app.state.runtime, run_id), endpoint=endpoint)
    return {"run_id": run_id, **export.as_dict()}
