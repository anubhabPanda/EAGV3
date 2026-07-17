"""Approach 2 demo webhook server for US-13 (see docs/WEBHOOK_ARCHITECTURE_OPTIONS.md).

Receives Meta/Twilio's raw HTTP POST directly and calls the WhatsApp adapter's
on_message()/send() directly. The GLC gateway is NOT in this path — its
allowlist/rate-limit/audit pipeline is bypassed. That's Approach 3 (out of
scope: shared glc/routes/channels.py, separate maintainer PR, post-US-15).

Run from repo root:
    uv run python glc/channels/catalogue/whatsapp/demo_webhook_server.py

Listens on port 8111 by default — same as `glc serve`'s default GLC_PORT,
since this script and the gateway are mutually exclusive (put this behind
ngrok and register the public URL + WHATSAPP_VERIFY_TOKEN in the Meta/Twilio
console).
Reads WHATSAPP_APP_SECRET, WHATSAPP_VERIFY_TOKEN, WHATSAPP_PHONE_NUMBER_ID,
WHATSAPP_TOKEN, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM,
TWILIO_WEBHOOK_URL from .env at the repo root (all read inside adapter.py
itself except WHATSAPP_VERIFY_TOKEN, which this script checks directly for
the hub.challenge handshake).
"""

from __future__ import annotations

import asyncio
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv


def _find_repo_root() -> Path:
    for p in Path(__file__).resolve().parents:
        if (p / "pyproject.toml").exists():
            return p
    raise RuntimeError("pyproject.toml not found — run from within the repo")


load_dotenv(_find_repo_root() / ".env")

from glc.channels.catalogue.whatsapp.adapter import (  # noqa: E402
    verify_meta_signature,
    verify_twilio_signature,
)
from glc.channels.envelope import ChannelReply  # noqa: E402
from glc.channels.registry import instantiate  # noqa: E402

VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "glc-verify-token-us1")
PORT = int(os.environ.get("WEBHOOK_PORT", "8111"))

adapter = instantiate("whatsapp")


def _classify_drop_reason(raw_body: bytes, headers: dict[str, str]) -> str:
    """Diagnostic-only re-check for the demo log — never affects on_message()'s
    own decision. Meta sends a separate delivery-status webhook (sent/
    delivered/read) for every message exchanged, which on_message() correctly
    drops (no "messages" key to parse) — that's expected, not a signature or
    trust failure, and the log line should say so rather than crying wolf.
    """
    lower_headers = {k.lower(): v for k, v in headers.items()}
    twilio_sig = lower_headers.get("x-twilio-signature", "")
    meta_sig = lower_headers.get("x-hub-signature-256", "")

    if twilio_sig:
        url = os.environ.get("TWILIO_WEBHOOK_URL", "")
        auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
        parsed = parse_qs(raw_body.decode("utf-8", errors="replace"), keep_blank_values=True)
        params = {k: v[0] if v else "" for k, v in parsed.items()}
        if not verify_twilio_signature(url, params, twilio_sig, auth_token):
            return "bad Twilio signature (X-Twilio-Signature did not verify)"
        if not params.get("WaId"):
            return "verified Twilio webhook but no WaId present (e.g. status callback)"
        return "verified Twilio webhook but content unusable (unexpected shape)"

    if meta_sig:
        if not verify_meta_signature(raw_body, headers):
            return "bad Meta signature (X-Hub-Signature-256 did not verify)"
        try:
            body = json.loads(raw_body)
            value = body["entry"][0]["changes"][0]["value"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            return "verified Meta webhook but unexpected payload shape"
        if not value.get("messages"):
            return (
                "verified Meta status callback (sent/delivered/read receipt) "
                "-- not an inbound message, no action needed"
            )
        return "verified Meta webhook but message content unusable (e.g. non-text type)"

    return "no recognized signature header -- not from Meta or Twilio"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        mode = (params.get("hub.mode") or [""])[0]
        token = (params.get("hub.verify_token") or [""])[0]
        challenge = (params.get("hub.challenge") or [""])[0]

        if mode == "subscribe" and token == VERIFY_TOKEN:
            print(f"[demo] verify OK - challenge={challenge!r}")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(challenge.encode())
        else:
            print(f"[demo] bad verify_token: got {token!r}, expected {VERIFY_TOKEN!r}")
            self.send_response(403)
            self.end_headers()

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length)
        headers = dict(self.headers.items())

        asyncio.run(self._handle_inbound(raw_body, headers))

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    async def _handle_inbound(self, raw_body: bytes, headers: dict[str, str]) -> None:
        msg = await adapter.on_message({"raw_body": raw_body, "headers": headers})
        if msg is None:
            print(f"[demo] dropped: {_classify_drop_reason(raw_body, headers)}")
            return

        print(
            f"[demo] inbound provider={msg.metadata.get('provider')} "
            f"from={msg.channel_user_id} trust={msg.trust_level} text={msg.text!r}"
        )

        # S11 stub agent: same echo behaviour as the gateway's own
        # /v1/channels/{name} endpoint and Approach 3's channel_webhook()
        # (see INBOUND_WEBHOOK_ARCHITECTURE.md) — the real agent runtime
        # is still a stub at this stage.
        reply = ChannelReply(
            channel=msg.channel,
            channel_user_id=msg.channel_user_id,
            text=f"[glc echo] {msg.text or ''}",
            thread_id=msg.thread_id,
        )
        result = await adapter.send(reply)
        print(f"[demo] send() result: {result}")

    def log_message(self, fmt, *args):  # silence default access log noise
        pass


if __name__ == "__main__":
    print(f"[demo] Approach 2 (US-13) server listening on port {PORT}")
    print(f"[demo] VERIFY_TOKEN = {VERIFY_TOKEN!r}")
    print(
        "[demo] gateway is NOT in this path (Approach 3 territory) - "
        "calls adapter.on_message()/adapter.send() directly"
    )
    HTTPServer(("", PORT), Handler).serve_forever()
