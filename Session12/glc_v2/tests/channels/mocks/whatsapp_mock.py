"""Mock-API fake for WhatsApp (Meta Cloud API).

Wire-format source:
  https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/payload-examples
  https://developers.facebook.com/docs/whatsapp/cloud-api/reference/messages
  https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/payload-examples#text-messages

Inbound: a webhook POST signed with `X-Hub-Signature-256: sha256=<hex>`
over the raw body using `APP_SECRET`. Body shape is
`{"object":"whatsapp_business_account","entry":[{"changes":[{"value":{"messages":[{...}], ...}}]}]}`.

Outbound: `POST https://graph.facebook.com/v20.0/{phone_number_id}/messages`
body — `{"messaging_product":"whatsapp","to":"<E164>","type":"text",
"text":{"body":"..."}}`.

Helpers
-------
queue_owner_message(text)            → owner-from text webhook envelope
queue_stranger_message(text)         → stranger-from text webhook envelope
queue_signed_webhook(body, secret)   → returns (body_bytes, headers)
                                       with a valid X-Hub-Signature-256
queue_unsigned_webhook(body)         → returns (body_bytes, headers)
                                       with no signature header
queue_tampered_webhook(body, secret) → returns (body_bytes, headers)
                                       with a deliberately wrong signature
"""

from __future__ import annotations

import hmac
import json
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any

OWNER_WA_ID = "919999990000"  # WhatsApp uses E.164 without the leading +.
STRANGER_WA_ID = "917777770000"
OWNER_ID = OWNER_WA_ID
STRANGER_ID = STRANGER_WA_ID

PHONE_NUMBER_ID = "10987654321"
WABA_ID = "98765432100"
DEFAULT_APP_SECRET = "test-app-secret"


def _text_webhook(
    *,
    from_wa_id: str,
    text: str,
    profile_name: str,
    message_id: str = "wamid.HBgL",
    timestamp: str = "1700000000",
) -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": WABA_ID,
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15555550100",
                                "phone_number_id": PHONE_NUMBER_ID,
                            },
                            "contacts": [{"profile": {"name": profile_name}, "wa_id": from_wa_id}],
                            "messages": [
                                {
                                    "from": from_wa_id,
                                    "id": message_id,
                                    "timestamp": timestamp,
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def _sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, sha256).hexdigest()


@dataclass
class WhatsappMock:
    """Synthetic Cloud API webhook + send endpoint."""

    inbound_events: list[dict[str, Any]] = field(default_factory=list)
    send_log: list[dict[str, Any]] = field(default_factory=list)
    constructed_envelopes: int = 0
    rate_limited: bool = False
    _disconnect_pending: bool = False
    app_secret: str = DEFAULT_APP_SECRET
    _next_msg: int = 100

    def _msg_id(self) -> str:
        self._next_msg += 1
        return f"wamid.HBgL{self._next_msg}"

    def queue_owner_message(self, text: str = "hello") -> dict[str, Any]:
        env = _text_webhook(
            from_wa_id=OWNER_WA_ID, text=text, profile_name="owner", message_id=self._msg_id()
        )
        self.inbound_events.append(env)
        return env

    def queue_stranger_message(self, text: str = "ping") -> dict[str, Any]:
        env = _text_webhook(
            from_wa_id=STRANGER_WA_ID, text=text, profile_name="stranger", message_id=self._msg_id()
        )
        self.inbound_events.append(env)
        return env

    def queue_signed_webhook(
        self, body: dict[str, Any] | None = None, text: str = "hi"
    ) -> tuple[bytes, dict[str, str]]:
        body = body if body is not None else self.queue_owner_message(text)
        raw = json.dumps(body, separators=(",", ":")).encode()
        return raw, {"X-Hub-Signature-256": _sign(raw, self.app_secret)}

    def queue_unsigned_webhook(
        self, body: dict[str, Any] | None = None, text: str = "hi"
    ) -> tuple[bytes, dict[str, str]]:
        body = body if body is not None else self.queue_owner_message(text)
        raw = json.dumps(body, separators=(",", ":")).encode()
        return raw, {}

    def queue_tampered_webhook(
        self, body: dict[str, Any] | None = None, text: str = "hi"
    ) -> tuple[bytes, dict[str, str]]:
        body = body if body is not None else self.queue_owner_message(text)
        raw = json.dumps(body, separators=(",", ":")).encode()
        # Sign with a *different* secret so the verification fails.
        return raw, {"X-Hub-Signature-256": _sign(raw, "WRONG-SECRET")}

    def record_envelope_constructed(self) -> None:
        """Called by the spike adapter and by inspectable adapters that
        want the test to be able to assert zero envelopes were built."""
        self.constructed_envelopes += 1

    async def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.rate_limited:
            # Real Cloud API throttle body.
            return {
                "error": {
                    "message": "(#80007) Rate limit hit",
                    "type": "OAuthException",
                    "code": 80007,
                },
                "status": 429,
            }
        self.send_log.append(payload)
        return {
            "messaging_product": "whatsapp",
            "contacts": [{"input": payload.get("to"), "wa_id": payload.get("to")}],
            "messages": [{"id": self._msg_id()}],
        }

    def force_disconnect(self) -> None:
        self._disconnect_pending = True

    def pop_disconnect(self) -> bool:
        was = self._disconnect_pending
        self._disconnect_pending = False
        return was
