"""Mock-API fake for the LINE Messaging API.

Wire-format source:
  https://developers.line.biz/en/reference/messaging-api/#message-event
  https://developers.line.biz/en/reference/messaging-api/#send-reply-message
  https://developers.line.biz/en/reference/messaging-api/#send-push-message

Inbound: a webhook POST body with `events[].type: "message"`,
`events[].source.userId`, `events[].message.text`, `events[].replyToken`.
Reply tokens are one-shot and expire ~60s after delivery.

Outbound: either `POST /v2/bot/message/reply` (cheap; uses a reply
token), or `POST /v2/bot/message/push` (counts against the monthly
push quota). The adapter must keep an in-memory TTL store of reply
tokens and prefer the reply endpoint when possible.

Helpers
-------
queue_owner_message(text)              → owner-from text event
queue_stranger_message(text)           → stranger-from text event
set_reply_token(user_id, token, ttl_s) → seed the adapter's TTL store
                                         (mirrors what the adapter does
                                         after parsing a webhook event)
consume_reply_token(user_id)           → mock-side read; the adapter
                                         calls this in the spike to
                                         decide reply vs push
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

OWNER_LINE_ID = "Uowner"
STRANGER_LINE_ID = "Ustranger"
OWNER_ID = OWNER_LINE_ID
STRANGER_ID = STRANGER_LINE_ID


def _webhook(
    *, user_id: str, text: str, reply_token: str, message_id: str = "100000000000"
) -> dict[str, Any]:
    return {
        "destination": "U01botdestination",
        "events": [
            {
                "type": "message",
                "mode": "active",
                "timestamp": 1700000000000,
                "source": {"type": "user", "userId": user_id},
                "webhookEventId": "01HEVT",
                "deliveryContext": {"isRedelivery": False},
                "replyToken": reply_token,
                "message": {"id": message_id, "type": "text", "text": text},
            }
        ],
    }


@dataclass
class LineMock:
    inbound_events: list[dict[str, Any]] = field(default_factory=list)
    send_log: list[dict[str, Any]] = field(default_factory=list)
    rate_limited: bool = False
    _disconnect_pending: bool = False
    _next_token: int = 1000
    # The mock's own TTL store, used by the spike adapter so the test
    # can observe whether the adapter consumed the token.
    reply_tokens: dict[str, tuple[str, float]] = field(default_factory=dict)

    def _token(self) -> str:
        self._next_token += 1
        return f"rt-{self._next_token}"

    def queue_owner_message(self, text: str = "hello") -> dict[str, Any]:
        tok = self._token()
        ev = _webhook(user_id=OWNER_LINE_ID, text=text, reply_token=tok)
        self.inbound_events.append(ev)
        self.set_reply_token(OWNER_LINE_ID, tok)
        return ev

    def queue_stranger_message(self, text: str = "ping") -> dict[str, Any]:
        tok = self._token()
        ev = _webhook(user_id=STRANGER_LINE_ID, text=text, reply_token=tok)
        self.inbound_events.append(ev)
        self.set_reply_token(STRANGER_LINE_ID, tok)
        return ev

    def set_reply_token(self, user_id: str, token: str, ttl_s: float = 60.0) -> None:
        self.reply_tokens[user_id] = (token, time.time() + ttl_s)

    def consume_reply_token(self, user_id: str) -> str | None:
        item = self.reply_tokens.pop(user_id, None)
        if item is None:
            return None
        token, expires = item
        if expires < time.time():
            return None
        return token

    async def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.rate_limited:
            return {"status": 429, "message": "Too Many Requests"}
        self.send_log.append(payload)
        return {"sentMessages": [{"id": f"sent-{len(self.send_log)}"}]}

    def force_disconnect(self) -> None:
        self._disconnect_pending = True

    def pop_disconnect(self) -> bool:
        was = self._disconnect_pending
        self._disconnect_pending = False
        return was
