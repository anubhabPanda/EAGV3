"""Tool-use loop wrapper around the gateway + MCP server.

When a Session 8 skill declares `tools_allowed: [...]` in agent_config.yaml,
its dispatch goes through `run_with_tools` (below) rather than a single
chat call. The wrapper drives the conversation until the model stops
asking for tool_calls and emits text:

    1. chat(messages, tools=schemas)
    2. if reply.tool_calls is non-empty:
         for each tc: dispatch via MCP, append a `role="tool"` message
         append assistant message with tool_calls
         go to 1
       else:
         return reply.text

The MCP server now supports both stdio and HTTP transport (like Session 7).
HTTP transport is the default for Session 8. Configure via environment:
    MCP_TRANSPORT=http (default)
    MCP_HTTP_URL=http://127.0.0.1:8008/mcp

This file is small on purpose. If the cost of a per-skill subprocess
becomes the bottleneck, the right fix is a shared session at the
Executor level, not a more clever client here.
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from gateway import LLM

MCP_SERVER = Path(__file__).parent / "mcp_server.py"
MAX_TOOL_HOPS = 6  # hard cap so a model that loves tool-use can't cost a fortune

# MCP Transport Configuration
MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", "http")  # stdio or http
MCP_HTTP_URL = os.environ.get("MCP_HTTP_URL", "http://127.0.0.1:8008/mcp")


@asynccontextmanager
async def _mcp_session():
    """
    Context manager for MCP server connection.

    Supports two transports:
    - http: Remote HTTP server (default for Session 8)
    - stdio: Local subprocess

    Set MCP_TRANSPORT=stdio to use stdio transport.
    Set MCP_HTTP_URL to customize the HTTP endpoint.
    """
    if MCP_TRANSPORT == "http":
        # HTTP transport - connect to remote server
        async with streamable_http_client(MCP_HTTP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
    else:
        # stdio transport - launch subprocess
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[str(MCP_SERVER)]
        )
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


async def _dispatch_tool(session: ClientSession, name: str, args: dict) -> str:
    """Run one MCP tool call and return its result as one text blob."""
    try:
        result = await session.call_tool(name, arguments=args)
    except Exception as e:
        return json.dumps({"error": f"{type(e).__name__}: {e}"})
    parts: list[str] = []
    for c in (getattr(result, "content", None) or []):
        t = getattr(c, "text", None)
        parts.append(t if t is not None else str(c))
    return "\n".join(parts) if parts else ""


async def run_with_tools(*, prompt: str, tools_payload: list[dict],
                         agent: str, session_id: str,
                         provider_pin: str | None = None,
                         max_tokens: int = 2048,
                         temperature: float = 0.3,
                         node_id: str = None,
                         tracer = None) -> dict:
    """Multi-turn chat: dispatch tool_calls via MCP, keep going until the
    model returns text. Returns the FINAL gateway reply dict (so callers
    can read `text`, `provider`, etc. the same way they would for a
    one-shot call).

    Args:
        node_id: Node ID for tracer logging
        tracer: Session8Tracer instance for logging tool calls
    """
    messages: list[dict] = [{"role": "user", "content": prompt}]
    last_reply: dict = {}

    async with _mcp_session() as mcp:
        for _ in range(MAX_TOOL_HOPS + 1):
            reply = await _chat(messages=messages, tools=tools_payload,
                                agent=agent, session_id=session_id,
                                provider_pin=provider_pin,
                                max_tokens=max_tokens, temperature=temperature)
            last_reply = reply
            tool_calls = reply.get("tool_calls") or []
            if not tool_calls:
                return reply
            # Carry the assistant's tool-call turn back through.
            messages.append({
                "role": "assistant",
                "content": reply.get("text", "") or "",
                "tool_calls": tool_calls,
            })
            for tc in tool_calls:
                # Log tool call via tracer
                if tracer and node_id:
                    tracer.tool_call(node_id, tc["name"], tc.get("arguments") or {})

                result_text = await _dispatch_tool(mcp, tc["name"],
                                                  tc.get("arguments") or {})

                # Log tool result via tracer
                if tracer and node_id:
                    truncated = len(result_text) > 8_000
                    display_result = result_text[:8_000] if truncated else result_text
                    tracer.tool_result(node_id, display_result, truncated)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": result_text[:8_000],  # cap per-tool reply
                })
    # Hit the hop cap. Return whatever the gateway last said.
    return last_reply


async def _chat(*, messages, tools, agent, session_id, provider_pin,
                max_tokens, temperature) -> dict:
    import asyncio as _a
    return await _a.to_thread(
        LLM().chat,
        messages=messages,
        tools=tools,
        tool_choice="auto",
        agent=agent,
        session=session_id,
        provider=provider_pin,
        max_tokens=max_tokens,
        temperature=temperature,
    )
