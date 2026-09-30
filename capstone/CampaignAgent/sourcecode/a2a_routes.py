"""GLC's inbound A2A surface: Agent Card discovery plus JSON-RPC task methods."""
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["A2A"])


@router.get("/.well-known/agent-card.json")
async def agent_card(request: Request):
    return await request.app.state.a2a_server.agent_card()


@router.post("/a2a")
async def a2a_rpc(request: Request):
    return await request.app.state.a2a_server.rpc(request)
