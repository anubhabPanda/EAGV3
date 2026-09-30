"""Run the twenty channel prompts through live GLC v5 -> S17 services.

The runner injects at GLC's canonical ChannelMessage WebSocket seam. It never
calls an adapter's outbound provider API, so a proof cannot contact real people.
Native provider payload conversion remains covered by each adapter's own suite.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import websockets
from channel_prompts import (
    REQUIRE_PARALLEL,
    REQUIRE_WAIT_RESUME,
    REQUIRED_TOOL_GROUPS,
    SCENARIOS,
    ChannelScenario,
)

FORBIDDEN_LIVE_DELIVERY_TOOLS = {"send_channel_message", "launch_job"}


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--glc", default=os.getenv("GLC_BASE_URL", "http://127.0.0.1:8121"))
    parser.add_argument("--s17", default=os.getenv("S17_BASE_URL", "http://127.0.0.1:8123"))
    parser.add_argument("--install-token", default=os.getenv("GLC_INSTALL_TOKEN"))
    parser.add_argument("--output", default="proofs/results/channel_stress_latest.json")
    parser.add_argument("--only", action="append", default=[])
    return parser.parse_args()


def _ws_url(base_url: str, channel: str, token: str) -> str:
    parsed = urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return f"{scheme}://{parsed.netloc}/v1/channels/{channel}?token={token}"


async def _pair_owner(client: httpx.AsyncClient, channel: str, token: str) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    issued = await client.post("/v1/control/pair", headers=headers, json={
        "channel": channel, "channel_user_id": "proof-owner", "user_handle": "proof-owner",
        "trust_level": "owner_paired",
    })
    issued.raise_for_status()
    confirmed = await client.post("/v1/control/pair/confirm", headers=headers,
                                  json={"code": issued.json()["code"]})
    confirmed.raise_for_status()


async def _send(glc: str, token: str, scenario: ChannelScenario, *, text: str,
                message_id: str, thread_id: str) -> dict[str, Any]:
    envelope = {
        "channel": scenario.channel,
        "channel_user_id": "proof-owner",
        "user_handle": "proof-owner",
        "text": text,
        "attachments": [],
        "voice_audio_ref": None,
        "thread_id": thread_id,
        # GLC overwrites this claim from its pairing store before S17 sees it.
        "trust_level": "untrusted",
        "arrived_at": datetime.now(UTC).isoformat(),
        "metadata": {"message_id": message_id, "proof_scenario": scenario.id},
    }
    async with websockets.connect(_ws_url(glc, scenario.channel, token), open_timeout=10) as socket:
        await socket.send(json.dumps(envelope))
        return json.loads(await asyncio.wait_for(socket.recv(), timeout=300))


async def _run_record(s17: httpx.AsyncClient, channel: str, message_id: str) -> tuple[dict, dict]:
    history = (await s17.get("/v1/agent/events")).json()["events"]
    record = next(item for item in reversed(history)
                  if item["event"]["source"] == f"glc.channel.{channel}"
                  and item["event"]["id"] == message_id)
    decision = record["decisions"][-1]
    run = (await s17.get(f"/v1/agent/runs/{decision['run_id']}")).json()
    return record, run


async def run_one(glc: str, token: str, s17: httpx.AsyncClient,
                  scenario: ChannelScenario, ordinal: int) -> dict[str, Any]:
    started = time.perf_counter()
    message_id = f"channel-proof-{ordinal:02d}-{int(time.time() * 1000)}"
    thread_id = f"proof-{scenario.id}"
    reply = await _send(glc, token, scenario, text=scenario.prompt,
                        message_id=message_id, thread_id=thread_id)
    record, run = await _run_record(s17, scenario.channel, message_id)
    final_decision = record["decisions"][-1]
    follow_up = None
    if scenario.follow_up:
        follow_id = f"{message_id}-approval"
        follow_reply = await _send(glc, token, scenario, text=scenario.follow_up,
                                   message_id=follow_id, thread_id=thread_id)
        follow_record, run = await _run_record(s17, scenario.channel, follow_id)
        final_decision = follow_record["decisions"][-1]
        follow_up = {"prompt": scenario.follow_up, "reply": follow_reply,
                     "decision": follow_record["decisions"][-1]}

    nodes = run.get("nodes", {})
    actual_tools = [node.get("skill") for node in nodes.values()]
    events = run.get("events", [])
    result = {
        "id": scenario.id,
        "channel": scenario.channel,
        "prompt": scenario.prompt,
        "why_agentic": scenario.why_agentic,
        "anticipated_tools": list(scenario.likely_tools),
        "actual_tools": actual_tools,
        "reply": reply,
        "follow_up": follow_up,
        "run_id": run.get("run_id"),
        "run_status": final_decision.get("run_status"),
        "finished": run.get("finished"),
        "event_count": len(events),
        "parallel_frontier": any(
            event.get("kind") == "graph_patched" and len(event.get("payload", {}).get("add", [])) > 1
            for event in events
        ),
        "waited": any(event.get("kind") == "task_waiting" for event in events),
        "resumed": any(event.get("kind") == "external_event_received" for event in events),
        "duration_s": round(time.perf_counter() - started, 3),
    }
    result["no_external_delivery"] = not bool(
        FORBIDDEN_LIVE_DELIVERY_TOOLS.intersection(actual_tools)
    )
    groups = REQUIRED_TOOL_GROUPS[scenario.id]
    result["requirements"] = [list(group) for group in groups]
    result["requirements_met"] = [bool(set(group).intersection(actual_tools)) for group in groups]
    result["passed"] = bool(
        reply.get("channel") == scenario.channel
        and reply.get("text")
        and result["run_id"]
        and result["run_status"] == "completed"
        and actual_tools
        and result["finished"]
        and all(result["requirements_met"])
        and result["no_external_delivery"]
        and (scenario.id not in REQUIRE_PARALLEL or result["parallel_frontier"])
        and (scenario.id not in REQUIRE_WAIT_RESUME or (result["waited"] and result["resumed"]))
    )
    return result


async def main() -> int:
    args = _args()
    if not args.install_token:
        raise SystemExit("GLC_INSTALL_TOKEN is required")
    selected = [item for item in SCENARIOS if not args.only or item.id in set(args.only)]
    async with httpx.AsyncClient(base_url=args.glc, timeout=20) as glc, \
               httpx.AsyncClient(base_url=args.s17, timeout=20) as s17:
        for channel in sorted({item.channel for item in selected}):
            await _pair_owner(glc, channel, args.install_token)
        results = []
        for ordinal, scenario in enumerate(selected, 1):
            try:
                result = await run_one(args.glc, args.install_token, s17, scenario, ordinal)
            except Exception as error:
                result = {"id": scenario.id, "channel": scenario.channel, "prompt": scenario.prompt,
                          "passed": False, "error": f"{type(error).__name__}: {error}"}
            results.append(result)
            print(json.dumps({key: result.get(key) for key in
                              ("id", "channel", "passed", "actual_tools", "duration_s", "error")
                              if result.get(key) is not None}, ensure_ascii=False), flush=True)

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "glc": args.glc,
        "s17": args.s17,
        "passed": sum(bool(item["passed"]) for item in results),
        "total": len(results),
        "results": results,
    }
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(destination), "passed": report["passed"],
                      "total": report["total"]}), flush=True)
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
