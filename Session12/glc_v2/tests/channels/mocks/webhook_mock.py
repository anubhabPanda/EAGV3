"""Mock-API fake for the generic Webhook (HTTP in/out) adapter.

Wire-format source (Stripe-style signed webhooks):
  https://stripe.com/docs/webhooks/signatures
  https://docs.svix.com/receiving/verifying-payloads/how-manual

Inbound: an HTTP POST with header
  `X-Webhook-Signature: t=<unix_ts>,v1=<hex hmac_sha256>`
where the signed string is `f"{t}.{body}"` and the HMAC key is the
per-integration shared secret. Bodies older than 5 minutes are
rejected to prevent replay attacks.

Outbound: an HTTP POST to a configured callback URL carrying the
agent's reply JSON.

Helpers
-------
queue_owner_message(text)             → owner-from JSON body
queue_stranger_message(text)          → stranger-from JSON body
queue_signed(body, secret, *, age_s)  → returns (body_bytes, headers)
                                        with the signature header
queue_unsigned(body)                  → returns (body_bytes, headers)
                                        with no signature header
queue_expired(body, secret)           → returns (body_bytes, headers)
                                        with a 10-minute-old timestamp
"""

from __future__ import annotations

import hmac
import json
import time
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any

OWNER_INT_ID = "external-system-1"
STRANGER_INT_ID = "external-system-2"
OWNER_ID = OWNER_INT_ID
STRANGER_ID = STRANGER_INT_ID

DEFAULT_SHARED_SECRET = "test-webhook-secret"
REPLAY_WINDOW_SECONDS = 5 * 60


def _sign(timestamp: int, body: bytes, secret: str) -> str:
    signed = f"{timestamp}.{body.decode('utf-8', 'replace')}".encode()
    digest = hmac.new(secret.encode(), signed, sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def _body(*, sender_id: str, handle: str, text: str) -> dict[str, Any]:
    return {
        "sender_id": sender_id,
        "sender_handle": handle,
        "text": text,
        "metadata": {"received_via": "webhook"},
    }


@dataclass
class WebhookMock:
    inbound_events: list[dict[str, Any]] = field(default_factory=list)
    send_log: list[dict[str, Any]] = field(default_factory=list)
    rate_limited: bool = False
    _disconnect_pending: bool = False
    shared_secret: str = DEFAULT_SHARED_SECRET

    def queue_owner_message(self, text: str = "hello") -> dict[str, Any]:
        body, headers = self.queue_signed(_body(sender_id=OWNER_INT_ID, handle="owner", text=text))
        ev = {"raw_body": body, "headers": headers}
        self.inbound_events.append(ev)
        return ev

    def queue_stranger_message(self, text: str = "ping") -> dict[str, Any]:
        body, headers = self.queue_signed(_body(sender_id=STRANGER_INT_ID, handle="stranger", text=text))
        ev = {"raw_body": body, "headers": headers}
        self.inbound_events.append(ev)
        return ev

    def queue_signed(
        self, body: dict[str, Any], *, age_s: int = 0, secret: str | None = None
    ) -> tuple[bytes, dict[str, str]]:
        secret = secret or self.shared_secret
        raw = json.dumps(body, separators=(",", ":")).encode()
        ts = int(time.time()) - age_s
        return raw, {"X-Webhook-Signature": _sign(ts, raw, secret)}

    def queue_unsigned(
        self, body: dict[str, Any] | None = None, text: str = "no signature"
    ) -> tuple[bytes, dict[str, str]]:
        body = body if body is not None else _body(sender_id=OWNER_INT_ID, handle="owner", text=text)
        raw = json.dumps(body, separators=(",", ":")).encode()
        return raw, {}

    def queue_expired(
        self, body: dict[str, Any] | None = None, text: str = "expired"
    ) -> tuple[bytes, dict[str, str]]:
        body = body if body is not None else _body(sender_id=OWNER_INT_ID, handle="owner", text=text)
        return self.queue_signed(body, age_s=REPLAY_WINDOW_SECONDS + 30)

    async def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.rate_limited:
            return {"status": 429, "error": "Too Many Requests"}
        self.send_log.append(payload)
        return {"status": 200, "id": f"webhook-{len(self.send_log)}"}

    def force_disconnect(self) -> None:
        self._disconnect_pending = True

    def pop_disconnect(self) -> bool:
        was = self._disconnect_pending
        self._disconnect_pending = False
        return was
