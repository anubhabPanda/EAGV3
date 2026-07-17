"""Mock-API fake for the Telegram Bot API.

Wire-format source:
  https://core.telegram.org/bots/api#update
  https://core.telegram.org/bots/api#message
  https://core.telegram.org/bots/api#sendmessage
  https://core.telegram.org/bots/api#getfile

Real Update / Message payloads are emitted by `queue_*` helpers. The
adapter parses them exactly as it would parse a long-poll batch from
`getUpdates`. The mock's `send()` accepts a `sendMessage` body and
records it in `send_log`; assertions in test_telegram.py check the
real wire fields (`chat_id`, `text`, `parse_mode`, `reply_markup`).

Helpers
-------
queue_owner_message(text)          → owner-from text Update
queue_stranger_message(text)       → stranger-from text Update
queue_photo_message(file_id, ...)  → owner-from photo Update with the
                                     given file_id in the largest size
get_file(file_id)                  → synthetic getFile response with
                                     `file_path` set; matches Telegram's
                                     real shape
send(payload)                      → records a sendMessage body
force_disconnect / pop_disconnect  → transport-level disconnect signal
                                     (used by the structural disconnect
                                     test)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Numeric Telegram user ids. The adapter stringifies them when
# constructing ChannelMessage.channel_user_id, so the trust-level
# classifier and the pairing store key on "42" / "999".
OWNER_TG_ID = 42
STRANGER_TG_ID = 999
OWNER_ID = str(OWNER_TG_ID)
STRANGER_ID = str(STRANGER_TG_ID)


def _make_message(
    *, from_id: int, username: str, text: str, chat_type: str = "private", message_id: int = 100
) -> dict[str, Any]:
    return {
        "message_id": message_id,
        "date": 1441645532,
        "chat": {"id": from_id, "type": chat_type, "username": username},
        "from": {"id": from_id, "is_bot": False, "username": username, "first_name": username.capitalize()},
        "text": text,
    }


def _make_photo_message(
    *, from_id: int, username: str, file_id: str, message_id: int = 200
) -> dict[str, Any]:
    return {
        "message_id": message_id,
        "date": 1441645540,
        "chat": {"id": from_id, "type": "private", "username": username},
        "from": {"id": from_id, "is_bot": False, "username": username},
        "caption": "look",
        "photo": [
            {
                "file_id": file_id + "_small",
                "file_unique_id": "uniq_s",
                "width": 90,
                "height": 60,
                "file_size": 1234,
            },
            {
                "file_id": file_id,
                "file_unique_id": "uniq_l",
                "width": 800,
                "height": 600,
                "file_size": 123456,
            },
        ],
    }


@dataclass
class TelegramMock:
    """Synthetic Telegram Bot API. Inbound shape mirrors getUpdates;
    outbound shape mirrors sendMessage."""

    inbound_events: list[dict[str, Any]] = field(default_factory=list)
    send_log: list[dict[str, Any]] = field(default_factory=list)
    rate_limited: bool = False
    _disconnect_pending: bool = False
    _next_update_id: int = 10_000
    _files: dict[str, dict[str, Any]] = field(default_factory=dict)

    def _next_id(self) -> int:
        self._next_update_id += 1
        return self._next_update_id

    def queue_owner_message(self, text: str = "hello") -> dict[str, Any]:
        update = {
            "update_id": self._next_id(),
            "message": _make_message(
                from_id=OWNER_TG_ID, username="owner", text=text, message_id=self._next_id()
            ),
        }
        self.inbound_events.append(update)
        return update

    def queue_stranger_message(self, text: str = "ping") -> dict[str, Any]:
        update = {
            "update_id": self._next_id(),
            "message": _make_message(
                from_id=STRANGER_TG_ID, username="stranger", text=text, message_id=self._next_id()
            ),
        }
        self.inbound_events.append(update)
        return update

    def queue_photo_message(
        self, file_id: str = "AgADBAADHKgxG4xnEUe", from_owner: bool = True
    ) -> dict[str, Any]:
        sender = (OWNER_TG_ID, "owner") if from_owner else (STRANGER_TG_ID, "stranger")
        update = {
            "update_id": self._next_id(),
            "message": _make_photo_message(
                from_id=sender[0], username=sender[1], file_id=file_id, message_id=self._next_id()
            ),
        }
        # Register the synthetic file_path that get_file will resolve.
        self._files[file_id] = {
            "file_id": file_id,
            "file_unique_id": "uniq_l",
            "file_size": 123456,
            "file_path": f"photos/file_{file_id}.jpg",
        }
        self.inbound_events.append(update)
        return update

    def get_file(self, file_id: str) -> dict[str, Any]:
        if file_id not in self._files:
            raise KeyError(f"unknown file_id: {file_id}")
        return dict(self._files[file_id])

    async def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.rate_limited:
            return {
                "status": 429,
                "error": "telegram: Too Many Requests",
                "ok": False,
                "error_code": 429,
                "parameters": {"retry_after": 30},
            }
        self.send_log.append(payload)
        # Real Telegram response shape: {"ok": true, "result": Message}
        return {
            "ok": True,
            "result": {
                "message_id": len(self.send_log) + 1000,
                "date": 1441645600,
                "chat": {"id": payload.get("chat_id"), "type": "private"},
                "text": payload.get("text", ""),
            },
        }

    def force_disconnect(self) -> None:
        self._disconnect_pending = True

    def pop_disconnect(self) -> bool:
        was = self._disconnect_pending
        self._disconnect_pending = False
        return was
