"""Capability workers for the campaign/subscriber MCP tools.

Every worker here does the same small thing: pull its declared arguments out
of ``task.input``, forward them to one named MCP tool, and return that tool's
JSON payload as the node's result. Which MCP tool a capability calls is bound
once in ``runtime.py`` via ``functools.partial(..., tool="EmailCampaign.list")``;
nothing here branches on a capability name, so adding a 29th tool is a
declaration in ``capabilities.py`` plus one partial binding, not a new worker.
"""
from __future__ import annotations

import json
from typing import Any

from sourcecode.core.live_graph import TaskSpec
from sourcecode.mcp_client import call_mcp_tool
from sourcecode.workers.context import RunContext

__all__ = ["run_list", "run_get", "run_create", "run_update", "run_delete",
           "run_transition", "run_preview", "run_public"]


def _parse_object(raw: str | None, *, field: str) -> dict[str, Any]:
    """Parse an optional JSON-object argument, e.g. ``fields`` or ``filters``."""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"{field} must be valid JSON: {error}") from error
    if not isinstance(parsed, dict):
        raise ValueError(f"{field} must be a JSON object")
    return parsed


def _records(result: dict[str, Any]) -> dict[str, Any]:
    """Normalise a list-style MCP response so downstream steps see a plain list."""
    data = result.get("data")
    records = data if isinstance(data, list) else []
    return {**result, "records": records, "count": len(records)}


async def run_list(ctx: RunContext, tool: str, task: TaskSpec) -> dict[str, Any]:
    params = {key: value for key, value in task.input.items() if key != "filters"}
    params.update(_parse_object(task.input.get("filters"), field="filters"))
    result = await call_mcp_tool(tool, **params)
    return _records(result)


async def run_get(ctx: RunContext, tool: str, task: TaskSpec) -> dict[str, Any]:
    return await call_mcp_tool(tool, id=task.input["id"])


async def run_create(ctx: RunContext, tool: str, task: TaskSpec) -> dict[str, Any]:
    return await call_mcp_tool(tool, **_parse_object(task.input["fields"], field="fields"))


async def run_update(ctx: RunContext, tool: str, task: TaskSpec) -> dict[str, Any]:
    fields = _parse_object(task.input.get("fields"), field="fields")
    return await call_mcp_tool(tool, id=task.input["id"], **fields)


async def run_delete(ctx: RunContext, tool: str, task: TaskSpec) -> dict[str, Any]:
    return await call_mcp_tool(tool, id=task.input["id"])


async def run_transition(ctx: RunContext, tool: str, task: TaskSpec) -> dict[str, Any]:
    """State-transition tools (schedule / pause / cancel / save_draft)."""
    fields = _parse_object(task.input.get("fields"), field="fields")
    return await call_mcp_tool(tool, id=task.input["id"], **fields)


async def run_preview(ctx: RunContext, tool: str, task: TaskSpec) -> dict[str, Any]:
    return await call_mcp_tool(tool, **_parse_object(task.input["criteria"], field="criteria"))


async def run_public(ctx: RunContext, tool: str, task: TaskSpec) -> dict[str, Any]:  # noqa: ARG001
    return await call_mcp_tool(tool)
