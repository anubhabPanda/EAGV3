"""Mock-API fake for the GLC WebUI in-browser chat.

Wire-format source:
  Course-defined; see docs/ADAPTER_GUIDE.md §WebUI for the protocol
  spec. The shape mirrors common WebSocket chat protocols (Slack RTM,
  Discord gateway, Mattermost).

Inbound: a WebSocket text frame with JSON
  `{"type": "user_message", "session_id", "text", "attachments"?}`
Outbound: two WebSocket text frames per reply:
  `{"type": "agent_reply", "text": "", "typing": true}`   (typing indicator)
  `{"type": "agent_reply", "text": "<reply>", "typing": false}`

The mock records every frame the adapter dispatches in `send_log`
so the behavioural test can assert the typing-indicator pre-frame
arrives before the final reply frame.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

OWNER_USER_ID = "owner"  # WebUI is owner-only by default.
STRANGER_USER_ID = "guest"
OWNER_ID = OWNER_USER_ID
STRANGER_ID = STRANGER_USER_ID

OWNER_SESSION = "browser-owner-001"
STRANGER_SESSION = "browser-guest-002"


def _user_message_frame(*, session_id: str, user_id: str, text: str) -> dict[str, Any]:
    return {
        "type": "user_message",
        "session_id": session_id,
        "user_id": user_id,
        "user_handle": "owner" if user_id == OWNER_USER_ID else "stranger",
        "text": text,
        "attachments": [],
        "client_ts": 1700000000000,
    }


@dataclass
class WebuiMock:
    inbound_events: list[dict[str, Any]] = field(default_factory=list)
    send_log: list[dict[str, Any]] = field(default_factory=list)
    rate_limited: bool = False
    _disconnect_pending: bool = False

    def queue_owner_message(self, text: str = "hello") -> dict[str, Any]:
        ev = _user_message_frame(session_id=OWNER_SESSION, user_id=OWNER_USER_ID, text=text)
        self.inbound_events.append(ev)
        return ev

    def queue_stranger_message(self, text: str = "ping") -> dict[str, Any]:
        ev = _user_message_frame(session_id=STRANGER_SESSION, user_id=STRANGER_USER_ID, text=text)
        self.inbound_events.append(ev)
        return ev

    async def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.rate_limited:
            return {"type": "error", "code": 429, "error": "rate limited", "status": 429}
        self.send_log.append(payload)
        return {"type": "ack", "id": f"frame-{len(self.send_log)}"}

    def force_disconnect(self) -> None:
        self._disconnect_pending = True

    def pop_disconnect(self) -> bool:
        was = self._disconnect_pending
        self._disconnect_pending = False
        return was
