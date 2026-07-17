"""Mock-API fake for the Discord Gateway + REST API.

Wire-format source:
  https://discord.com/developers/docs/topics/gateway-events#message-create
  https://discord.com/developers/docs/resources/channel#create-message
  https://discord.com/developers/docs/resources/user#user-object

The Gateway delivers JSON dispatch frames `{"op": 0, "t": "<EVENT>", "s": N, "d": {...}}`.
The REST send target is `POST /channels/{channel.id}/messages`. We model
both: `queue_owner_message` emits a MESSAGE_CREATE dispatch frame; `send()`
records the REST body the adapter would POST.

Helpers
-------
queue_owner_message(text)              → MESSAGE_CREATE dispatch (owner)
queue_stranger_message(text)           → MESSAGE_CREATE dispatch (stranger)
queue_mention_message(mentioned_user)  → MESSAGE_CREATE with <@id> in
                                         content and the User in `mentions`
register_user(user_id, username)       → seed the user directory the
                                         adapter resolves via get_user()
get_user(user_id)                      → returns a Discord User object,
                                         or None if unknown
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

OWNER_DISCORD_ID = "42"  # Discord snowflakes are strings.
STRANGER_DISCORD_ID = "999"
OWNER_ID = OWNER_DISCORD_ID
STRANGER_ID = STRANGER_DISCORD_ID

GUILD_ID = "111222333"
CHANNEL_ID = "444555666"


def _user(user_id: str, username: str, discriminator: str = "0001") -> dict[str, Any]:
    return {
        "id": user_id,
        "username": username,
        "discriminator": discriminator,
        "global_name": username.capitalize(),
        "avatar": None,
        "bot": False,
    }


def _message_create(
    *,
    author: dict[str, Any],
    content: str,
    mentions: list[dict[str, Any]] | None = None,
    message_id: str = "msg-1",
) -> dict[str, Any]:
    return {
        "op": 0,
        "t": "MESSAGE_CREATE",
        "s": 1,
        "d": {
            "id": message_id,
            "channel_id": CHANNEL_ID,
            "guild_id": GUILD_ID,
            "author": author,
            "content": content,
            "timestamp": "2026-06-17T12:00:00.000000+00:00",
            "edited_timestamp": None,
            "tts": False,
            "mention_everyone": False,
            "mentions": mentions or [],
            "mention_roles": [],
            "attachments": [],
            "embeds": [],
            "type": 0,
        },
    }


@dataclass
class DiscordMock:
    """Synthetic Discord gateway + REST."""

    inbound_events: list[dict[str, Any]] = field(default_factory=list)
    send_log: list[dict[str, Any]] = field(default_factory=list)
    rate_limited: bool = False
    _disconnect_pending: bool = False
    _users: dict[str, dict[str, Any]] = field(default_factory=dict)
    _next_message_id: int = 100

    def __post_init__(self) -> None:
        # Seed the owner and stranger in the user directory.
        self.register_user(OWNER_DISCORD_ID, "owner")
        self.register_user(STRANGER_DISCORD_ID, "stranger")

    def _msg_id(self) -> str:
        self._next_message_id += 1
        return str(self._next_message_id)

    def register_user(self, user_id: str, username: str) -> None:
        self._users[user_id] = _user(user_id, username)

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        u = self._users.get(user_id)
        return dict(u) if u else None

    def queue_owner_message(self, text: str = "hello") -> dict[str, Any]:
        ev = _message_create(author=self._users[OWNER_DISCORD_ID], content=text, message_id=self._msg_id())
        self.inbound_events.append(ev)
        return ev

    def queue_stranger_message(self, text: str = "ping") -> dict[str, Any]:
        ev = _message_create(author=self._users[STRANGER_DISCORD_ID], content=text, message_id=self._msg_id())
        self.inbound_events.append(ev)
        return ev

    def queue_mention_message(
        self, mentioned_user_id: str = "123456789", mentioned_username: str = "alice"
    ) -> dict[str, Any]:
        """Owner sends a message that mentions another user. Discord
        formats this as `<@USERID>` inline plus a `mentions` array of
        User objects in the dispatch payload."""
        if mentioned_user_id not in self._users:
            self.register_user(mentioned_user_id, mentioned_username)
        content = f"hey <@{mentioned_user_id}> can you help?"
        ev = _message_create(
            author=self._users[OWNER_DISCORD_ID],
            content=content,
            mentions=[self._users[mentioned_user_id]],
            message_id=self._msg_id(),
        )
        self.inbound_events.append(ev)
        return ev

    async def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.rate_limited:
            # Real Discord 429 body shape.
            return {
                "status": 429,
                "message": "You are being rate limited.",
                "retry_after": 1.234,
                "global": False,
                "code": 0,
            }
        self.send_log.append(payload)
        return {
            "id": self._msg_id(),
            "channel_id": CHANNEL_ID,
            "content": payload.get("content", ""),
            "tts": False,
            "type": 0,
        }

    def force_disconnect(self) -> None:
        self._disconnect_pending = True

    def pop_disconnect(self) -> bool:
        was = self._disconnect_pending
        self._disconnect_pending = False
        return was
