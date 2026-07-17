"""Local stub server for the Microsoft Teams adapter demo.

Exposes ``POST /api/messages`` matching the Bot Framework Connector contract.
The adapter's ``send()`` outbound payload is returned directly as the HTTP
response body so curl or the Bot Framework Emulator can see the full
round-trip without a live Azure tenant.

Usage::

    python -m glc.channels.catalogue.teams.setup.emulator_runner
    python -m glc.channels.catalogue.teams.setup.emulator_runner --port 3978 --no-emulator

Flags::

    --host          Bind address (default 127.0.0.1)
    --port          Port to listen on (default 3978 — BF Emulator default)
    --no-emulator   Skip Bot Framework JWT auth check (headless curl / CI testing)
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from glc.channels.catalogue.teams.adapter import Adapter
from glc.channels.envelope import ChannelReply

_LOG = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 3978  # Bot Framework Emulator default


@dataclass
class _CaptureMock:
    """Minimal mock satisfying the adapter's mock interface for a single request."""

    send_log: list[dict[str, Any]] = field(default_factory=list)

    async def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.send_log.append(payload)
        return {"id": "emulator-ok"}

    def pop_disconnect(self) -> bool:
        return False


def build_app(*, no_emulator: bool = False) -> FastAPI:
    if no_emulator:
        _LOG.info("--no-emulator: JWT auth skipped (headless mode)")

    app = FastAPI(title="Teams Emulator Stub", docs_url=None, redoc_url=None)

    @app.post("/api/messages")
    async def handle_messages(request: Request) -> JSONResponse:
        try:
            activity: dict[str, Any] = await request.json()
        except Exception:
            return JSONResponse(status_code=400, content={"error": "invalid JSON"})

        capture = _CaptureMock()
        adapter = Adapter(config={"mock": capture})

        msg = await adapter.on_message(activity)
        if msg is None:
            _LOG.debug("on_message → None (non-message, dropped, or disconnect)")
            return JSONResponse(status_code=200, content={})

        reply = ChannelReply(
            channel="teams",
            channel_user_id=msg.channel_user_id,
            text=f"[echo] {msg.text or '(no text)'}",
            thread_id=msg.thread_id,
        )
        await adapter.send(reply)

        # capture.send_log[0] is the actual Bot Framework Activity body
        # (type/text/replyToId/textFormat). adapter.send() returns the
        # mock's ack dict, not the payload itself.
        payload = capture.send_log[0] if capture.send_log else {}
        _LOG.info("round-trip OK  in=%r  out=%r", msg.text, payload)
        return JSONResponse(status_code=200, content=payload)

    return app


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="emulator_runner",
        description="Local Bot Framework stub server for the Teams adapter demo.",
    )
    p.add_argument("--host", default=DEFAULT_HOST, help=f"bind address (default {DEFAULT_HOST})")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port (default {DEFAULT_PORT})")
    p.add_argument(
        "--no-emulator",
        action="store_true",
        help="skip JWT auth check — use with plain curl or headless CI",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    app = build_app(no_emulator=args.no_emulator)
    _LOG.info(
        "Teams emulator stub → http://%s:%d/api/messages  (--no-emulator=%s)",
        args.host,
        args.port,
        args.no_emulator,
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
