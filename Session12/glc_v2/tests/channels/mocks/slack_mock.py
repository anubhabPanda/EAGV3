"""Mock-API fake for the Slack Events API + Web API.

Wire-format source:
  https://api.slack.com/events/message
  https://api.slack.com/methods/chat.postMessage
  https://api.slack.com/events-api#event_type_structure

Inbound: an Events API HTTP POST body wrapping a `message` event.
Outbound: a `chat.postMessage` body — `channel`, `text`, and the
optional `thread_ts` that controls threading.

Helpers
-------
queue_owner_message(text)              → event_callback wrapping a
                                         `message` event from owner
queue_stranger_message(text)           → same, from a stranger
queue_threaded_message(text, ts)       → message with `thread_ts` set,
                                         used by the behavioural test
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

TEAM_ID = "T01TEAM"
CHANNEL_ID = "C01CHAN"
OWNER_SLACK_ID = "U42"
STRANGER_SLACK_ID = "U999"
OWNER_ID = OWNER_SLACK_ID
STRANGER_ID = STRANGER_SLACK_ID


def _event_callback(
    *, user: str, text: str, ts: str = "1700000000.000100", thread_ts: str | None = None
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "type": "message",
        "channel": CHANNEL_ID,
        "user": user,
        "text": text,
        "ts": ts,
        "team": TEAM_ID,
        "channel_type": "channel",
    }
    if thread_ts:
        event["thread_ts"] = thread_ts
    return {
        "token": "verification-token",
        "team_id": TEAM_ID,
        "api_app_id": "A01APP",
        "event": event,
        "type": "event_callback",
        "event_id": "Ev01",
        "event_time": 1700000000,
        "authorizations": [
            {"team_id": TEAM_ID, "user_id": "USELF", "is_bot": True, "is_enterprise_install": False}
        ],
    }


@dataclass
class SlackMock:
    inbound_events: list[dict[str, Any]] = field(default_factory=list)
    send_log: list[dict[str, Any]] = field(default_factory=list)
    rate_limited: bool = False
    _disconnect_pending: bool = False
    _ts_counter: int = 100

    def _next_ts(self) -> str:
        self._ts_counter += 1
        return f"1700000000.{self._ts_counter:06d}"

    def queue_owner_message(self, text: str = "hello") -> dict[str, Any]:
        ev = _event_callback(user=OWNER_SLACK_ID, text=text, ts=self._next_ts())
        self.inbound_events.append(ev)
        return ev

    def queue_stranger_message(self, text: str = "ping") -> dict[str, Any]:
        ev = _event_callback(user=STRANGER_SLACK_ID, text=text, ts=self._next_ts())
        self.inbound_events.append(ev)
        return ev

    def queue_threaded_message(
        self, text: str = "in thread", thread_ts: str = "1700000000.000050"
    ) -> dict[str, Any]:
        ev = _event_callback(user=OWNER_SLACK_ID, text=text, ts=self._next_ts(), thread_ts=thread_ts)
        self.inbound_events.append(ev)
        return ev

    async def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.rate_limited:
            # Real Slack 429 — they also set Retry-After as a header in
            # practice; the body carries `ok: false`.
            return {"ok": False, "error": "ratelimited", "status": 429}
        self.send_log.append(payload)
        return {
            "ok": True,
            "channel": payload.get("channel"),
            "ts": self._next_ts(),
            "message": {"text": payload.get("text", ""), "type": "message"},
        }

    def force_disconnect(self) -> None:
        self._disconnect_pending = True

    def pop_disconnect(self) -> bool:
        was = self._disconnect_pending
        self._disconnect_pending = False
        return was
