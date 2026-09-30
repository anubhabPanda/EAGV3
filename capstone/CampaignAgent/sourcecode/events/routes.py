from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from sourcecode.auth import require_control

from .models import EventEnvelope, Subscription
from .report import liveness_status, morning_report, render_markdown

router = APIRouter(prefix="/v1/agent", tags=["autonomous events"])


# A subscription is the authority object of this whole session: it carries the
# instruction, the allowed side effects and the budget. Writing one is a
# control-plane action, not an anonymous one.
@router.put("/subscriptions/{subscription_id}", dependencies=[Depends(require_control)])
async def put_subscription(subscription_id: str, body: Subscription, request: Request):
    if body.id != subscription_id:
        raise HTTPException(422, "path id and body id differ")
    stored = request.app.state.event_store.put_subscription(body)
    return {"accepted": True, "subscription": stored}


@router.get("/subscriptions")
async def subscriptions(request: Request):
    return {"subscriptions": [item.model_dump(mode="json")
                              for item in request.app.state.event_store.subscriptions()]}


# Delivering an event is asking the agent to spend money on your behalf. Edge
# verification (HMAC per provider) still belongs at the adapter in front of this
# route; this token is the floor beneath it, not a replacement for it.
@router.post("/events", dependencies=[Depends(require_control)])
async def ingest_event(body: EventEnvelope, request: Request):
    return await request.app.state.event_engine.process(
        body,
        llm=lambda prompt, system: request.app.state.gateway.complete(prompt, system),
        transport=request.app.state.gateway,
    )


@router.get("/events")
async def event_history(request: Request, after: int = Query(default=0, ge=0)):
    return {"events": request.app.state.event_store.events(after=after)}


@router.get("/events/stream")
async def stream_events(request: Request, after: int = Query(default=0, ge=0)):
    """Live telemetry with cursor replay: reconnect with the last sequence."""
    async def generate():
        cursor = after
        while not await request.is_disconnected():
            records = request.app.state.event_store.events(after=cursor)
            if not records:
                yield ": keepalive\n\n"
                await asyncio.sleep(0.5)
                continue
            for record in records:
                cursor = record["sequence"]
                yield f"id: {cursor}\nevent: autonomous_event\ndata: {json.dumps(record)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/liveness")
async def liveness(request: Request):
    """Is the watcher alive, or merely quiet?

    A dashboard showing no work means either "nothing needed doing" or "the
    process that would have noticed is dead". Those must not look the same, so
    the beat is published and its *absence* is the alarm.
    """
    status = liveness_status(request.app.state.event_store)
    return JSONResponse(status, status_code=200 if status["alive"] else 503)


@router.get("/report")
async def report(request: Request, hours: int = Query(default=24, ge=1, le=720),
                 fmt: str = Query(default="json", pattern="^(json|markdown)$")):
    """The human-reviewable account of a period nobody watched."""
    since = datetime.now(UTC) - timedelta(hours=hours)
    document = morning_report(request.app.state.event_store, since=since)
    if fmt == "markdown":
        return PlainTextResponse(render_markdown(document))
    return document


@router.get("/refusals")
async def refusals(request: Request, hours: int = Query(default=24, ge=1, le=720)):
    """Work a control prevented. Without this endpoint it leaves no trace."""
    since = datetime.now(UTC) - timedelta(hours=hours)
    return {"refusals": request.app.state.event_store.refusals(since=since)}
