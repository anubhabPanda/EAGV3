"""A thin, token-authenticated client for the campaign/subscriber MCP server.

The MCP server exposes generic CRUD-style tools (``EmailCampaign.list``,
``Subscriber.create``, ...) over streamable HTTP with bearer-token auth. This
module owns exactly that connection: build a transport from two environment
variables, call one named tool with keyword arguments, and return its parsed
JSON payload. Capability workers in ``sourcecode/workers/campaign.py`` are the
only callers; nothing here decides which tool to call or with what arguments.
"""
from __future__ import annotations

import json
import os
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport


class McpConfigError(RuntimeError):
    """The MCP server URL or token is not configured."""


class McpToolError(RuntimeError):
    """The MCP server reported a tool-call failure."""


def _transport() -> StreamableHttpTransport:
    url = os.getenv("S17_MCP_URL")
    token = os.getenv("S17_MCP_TOKEN")
    if not url or not token:
        raise McpConfigError("campaign tools require S17_MCP_URL and S17_MCP_TOKEN")
    return StreamableHttpTransport(
        url=url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )


async def call_mcp_tool(tool_name: str, **params: Any) -> dict[str, Any]:
    """Call one MCP tool by name and return its decoded JSON result.

    Empty/None parameters are dropped before the call so a worker can always
    pass every declared argument, whether or not the user supplied it.
    """
    clean = {key: value for key, value in params.items() if value is not None and value != ""}
    async with Client(transport=_transport()) as client:
        result = await client.call_tool(tool_name, clean)
    if not result.content:
        return {}
    text = result.content[0].text
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {"raw_response": text}
    if isinstance(payload, dict) and payload.get("error"):
        raise McpToolError(f"{tool_name}: {payload['error']}")
    return payload if isinstance(payload, dict) else {"result": payload}
