"""HTTP + SSE UI surface, folded into the agent runtime (carried forward from S14).

  GET  /v1/catalog                  the trusted component catalog
  GET  /v1/runs/{id}/surface        build + validate a declarative surface
  GET  /v1/runs/{id}/snapshot       the complete data model as one STATE_SNAPSHOT
  GET  /v1/runs/{id}/events         AG-UI event stream over SSE
  GET  /v1/runs/{id}/composed       the interface the agent composed for a run
  POST /v1/validate                 validate an arbitrary surface (injection wall)
  POST /v1/action                   a validated user action (approve/reject/rerun)
  GET  /s/{id}                      the render client, pointed at a run

The data source is the runtime's own graph, read in-process off
``request.app.state.runtime`` — the same attribute ``GET /v1/agent/runs/{id}``
reads. No HTTP hop, no second service.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from .agui import run_data_model, state_snapshot, to_agui_event
from .catalog import catalog_manifest
from .hitl import PendingAction, decide_resume
from .surface import build_run_surface
from .validator import validate_surface

router = APIRouter()
_CLIENT = Path(__file__).parent / "client" / "index.html"


def _read_run(request: Request, run_id: str) -> dict:
    """Read one run from the runtime's in-process graph, in S13's journal shape.

    Mirrors S13's ``GET /v1/agent/runs/{id}``: ``{run_id, finished, nodes,
    edges, events}``. Events are ``Event(sequence, kind, node_id, payload)``
    dataclasses; convert to plain dicts so the UI builders see the same shape a
    recorded fixture carries.
    """
    runtime = request.app.state.runtime
    try:
        snapshot = runtime.graph.snapshot(run_id)
    except KeyError:
        raise HTTPException(404, "run not found") from None
    events = [
        {"sequence": e.sequence, "kind": e.kind, "node_id": e.node_id, "payload": e.payload}
        for e in runtime.graph.events(run_id)
    ]
    return {
        "run_id": run_id,
        "finished": snapshot.finished,
        "nodes": snapshot.nodes,
        "edges": snapshot.edges,
        "events": events,
    }


@router.get("/v1/catalog")
async def catalog():
    return catalog_manifest()


@router.get("/v1/runs/{run_id}/surface")
async def surface(run_id: str, request: Request):
    run = _read_run(request, run_id)
    built = build_run_surface(run)
    result = validate_surface(built)
    # The builder's own surface is always clean; validating it here proves the
    # service treats even its own output as untrusted before serving.
    return {
        "run_id": run_id,
        "surface": {"root": built["root"], "components": result.accepted, "dataModel": built["dataModel"]},
        "rejections": [r.as_dict() for r in result.rejections],
    }


@router.get("/v1/runs/{run_id}/snapshot")
async def snapshot(run_id: str, request: Request):
    """The COMPLETE current data model as a single AG-UI STATE_SNAPSHOT event.

    A client that reconnects fetches this once and is whole, instead of replaying
    the entire event tape. The data model is the fold of the run's own AG-UI
    stream (``run_data_model``), so it is byte-identical to what a full delta
    replay would produce. We also build the run's surface in-process so the
    caller learns how many components that state renders into.
    """
    run = _read_run(request, run_id)
    built = build_run_surface(run)  # in-process graph read, same source as /surface
    data_model = run_data_model(run)
    return {
        "run_id": run_id,
        "event": state_snapshot(data_model),
        "component_count": len(built["components"]),
    }


@router.get("/v1/runs/{run_id}/events")
async def events(run_id: str, request: Request, reconnect: int = 0, after: int = 0):
    run = _read_run(request, run_id)
    # On reconnect the stream leads with ONE STATE_SNAPSHOT carrying the full
    # current data model; the client rebuilds from that single frame rather than
    # folding every delta again. Normal (first-connect) streaming is unchanged.
    snap = run_data_model(run) if reconnect else None

    async def gen():
        cursor = after
        if snap is not None:
            yield f"data: {json.dumps(state_snapshot(snap, seq=cursor))}\n\n"
        while not await request.is_disconnected():
            current = _read_run(request, run_id)
            fresh = [event for event in current["events"] if event["sequence"] > cursor]
            for event in fresh:
                cursor = event["sequence"]
                yield f"id: {cursor}\ndata: {json.dumps(to_agui_event(event))}\n\n"
            if current["finished"]:
                yield f"data: {json.dumps({'type': 'RUN_FINISHED', 'seq': cursor + 1, 'source_kind': 'derived'})}\n\n"
                break
            if not fresh:
                yield ": keepalive\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(gen(), media_type="text/event-stream")


class ValidateBody(BaseModel):
    surface: dict


@router.post("/v1/validate")
async def validate(body: ValidateBody):
    result = validate_surface(body.surface)
    return {
        "ok": result.ok,
        "accepted": [c.get("id") for c in result.accepted],
        "rejections": [r.as_dict() for r in result.rejections],
    }


class ActionBody(BaseModel):
    run_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    args: dict = Field(default_factory=dict)
    # In a live system the pending params come from the parked node in S13. For
    # the recorded demo the caller supplies them so the binding check is real.
    pending_params: dict = Field(default_factory=dict)
    pending_summary: str = ""


@router.post("/v1/action")
async def action(body: ActionBody, request: Request):
    try:
        node = request.app.state.runtime.graph.snapshot(body.run_id).nodes[body.node_id]
    except (KeyError, TypeError):
        raise HTTPException(404, "waiting graph node not found") from None
    if node.get("state") != "waiting" or not isinstance(node.get("wait"), dict):
        raise HTTPException(409, "graph node is not waiting for a decision")
    wait = node["wait"]
    # The binding comes from the durable node, never from client-supplied
    # pending_params. Event payload cannot rewrite what the agent asked.
    bound = wait.get("params") if isinstance(wait.get("params"), dict) else {}
    pending = PendingAction(body.run_id, body.node_id, str(wait.get("question", "")), bound)
    decision = decide_resume(pending, body.action, body.args)
    if not decision.allowed:
        # A tamper attempt is refused; the node stays waiting.
        raise HTTPException(409, decision.reason)
    completion = request.app.state.runtime.graph.complete_waiting(
        str(wait["handle"]), str(wait["event_type"]),
        {"action": body.action, "args": body.args}, success=body.action == "approve",
    )
    if completion is None:
        return {"resumed": False, "duplicate": True, "node_id": body.node_id}
    result = await request.app.state.runtime.run(
        prompt=None, scope=None,
        llm=lambda prompt, system: request.app.state.gateway.complete(prompt, system),
        source_uri=None, source_author=None, run_id=body.run_id, resume=True,
    )
    return {"resumed": True, "node_id": body.node_id, "reason": decision.reason, "run": result}


@router.get("/v1/runs/{run_id}/composed")
async def composed(run_id: str, request: Request):
    """The interface the agent COMPOSED for this run (the compose_surface node's
    output), re-validated. Distinct from /surface, which is the run's progress
    view. This is what a UI-only app renders."""
    run = _read_run(request, run_id)
    node = run["nodes"].get("surface") or {}
    res = node.get("result") or {}
    surf = res.get("surface") or {}
    if not surf.get("components"):
        raise HTTPException(404, "run has no composed interface (no compose_surface node)")
    result = validate_surface(surf)
    return {
        "run_id": run_id,
        "finished": run["finished"],
        "surface": {"root": surf.get("root"), "components": result.accepted,
                    "dataModel": res.get("data_model") or surf.get("dataModel") or {}},
        "component_count": len(result.accepted),
        "clean": result.ok,
        "provider": res.get("provider"),
        "model": res.get("model"),
    }


@router.get("/s/{run_id}", response_class=HTMLResponse)
async def client(run_id: str):
    if not _CLIENT.exists():
        raise HTTPException(500, "render client missing")
    return _CLIENT.read_text().replace("__RUN_ID__", run_id)


@router.get("/console", response_class=HTMLResponse)
@router.get("/console/", response_class=HTMLResponse)
async def autonomy_console():
    """The operator page for a system nobody is watching.

    Session 9 of the lesson promises "a browser or operations page that
    reconnects with after=41". This is it: a projection of the durable event
    history, with the liveness beat as its loudest element, because a quiet
    console and a dead watcher must not render the same.

    Read-only on purpose. Every write path needs the control token and has no
    button here; an operator page that could create authority would be the very
    hole the control plane exists to close.
    """
    path = Path(__file__).parent / "client" / "console.html"
    if not path.exists():
        raise HTTPException(500, "autonomy console missing")
    return path.read_text()


@router.get("/app", response_class=HTMLResponse)
@router.get("/app/", response_class=HTMLResponse)
async def app_viewer():
    """A bare-minimal UI-only app shell: it starts a run, renders the composed
    interface, and turns a tap into the next turn. The protocol does the work."""
    path = Path(__file__).parent / "client" / "app.html"
    if not path.exists():
        raise HTTPException(500, "app viewer missing")
    return path.read_text()
