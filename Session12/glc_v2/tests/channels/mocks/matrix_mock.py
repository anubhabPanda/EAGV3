"""Mock-API fake for Matrix client-server API.

Wire-format source:
  https://spec.matrix.org/v1.10/client-server-api/#mroommessage
  https://spec.matrix.org/v1.10/client-server-api/#put_matrixclientv3roomsroomidsendeventtypetxnid
  https://spec.matrix.org/v1.10/client-server-api/#mxc-uris

Inbound: a `/sync` response containing one `room.message` event with
`content.msgtype: "m.text"` and `content.body`.
Outbound: a `PUT /_matrix/client/v3/rooms/{roomId}/send/m.room.message/{txnId}`
body — `{msgtype: "m.text", body: "..."}`.

Helpers
-------
queue_owner_message(text)       → m.text event from owner
queue_stranger_message(text)    → m.text event from stranger
queue_image_message(mxc_url)    → m.image event with the given mxc:// URL
download_media(mxc_url)         → synthetic bytes for an mxc:// URI
                                  (returned via /_matrix/media/v3/download)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

OWNER_MX_ID = "@owner:matrix.org"
STRANGER_MX_ID = "@stranger:matrix.org"
OWNER_ID = OWNER_MX_ID
STRANGER_ID = STRANGER_MX_ID

ROOM_ID = "!abcdef:matrix.org"


def _room_message(
    *,
    sender: str,
    body: str,
    msgtype: str = "m.text",
    event_id: str = "$evt-1",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    content: dict[str, Any] = {"msgtype": msgtype, "body": body}
    if extra:
        content.update(extra)
    return {
        "type": "m.room.message",
        "sender": sender,
        "room_id": ROOM_ID,
        "event_id": event_id,
        "origin_server_ts": 1700000000000,
        "content": content,
        "unsigned": {"age": 50},
    }


def _sync_response(events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "next_batch": "s1_2_3",
        "rooms": {
            "join": {
                ROOM_ID: {
                    "timeline": {"events": events, "limited": False, "prev_batch": "p"},
                    "state": {"events": []},
                    "ephemeral": {"events": []},
                    "account_data": {"events": []},
                    "unread_notifications": {"highlight_count": 0, "notification_count": 0},
                }
            }
        },
    }


@dataclass
class MatrixMock:
    inbound_events: list[dict[str, Any]] = field(default_factory=list)
    send_log: list[dict[str, Any]] = field(default_factory=list)
    rate_limited: bool = False
    _disconnect_pending: bool = False
    _next_event: int = 100
    _media: dict[str, bytes] = field(default_factory=dict)

    def _evt_id(self) -> str:
        self._next_event += 1
        return f"$evt-{self._next_event}"

    def queue_owner_message(self, text: str = "hello") -> dict[str, Any]:
        ev = _sync_response([_room_message(sender=OWNER_MX_ID, body=text, event_id=self._evt_id())])
        self.inbound_events.append(ev)
        return ev

    def queue_stranger_message(self, text: str = "ping") -> dict[str, Any]:
        ev = _sync_response([_room_message(sender=STRANGER_MX_ID, body=text, event_id=self._evt_id())])
        self.inbound_events.append(ev)
        return ev

    def queue_image_message(
        self, mxc_url: str = "mxc://matrix.org/abc123", body: str = "photo.png"
    ) -> dict[str, Any]:
        # Register synthetic content bytes for the mxc URI.
        self._media[mxc_url] = b"\x89PNG\r\n\x1a\n synthetic image bytes"
        ev = _sync_response(
            [
                _room_message(
                    sender=OWNER_MX_ID,
                    body=body,
                    msgtype="m.image",
                    event_id=self._evt_id(),
                    extra={"url": mxc_url, "info": {"mimetype": "image/png", "size": 42}},
                )
            ]
        )
        self.inbound_events.append(ev)
        return ev

    def download_media(self, mxc_url: str) -> bytes:
        if mxc_url not in self._media:
            raise KeyError(f"unknown mxc URI: {mxc_url}")
        return self._media[mxc_url]

    async def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.rate_limited:
            # Real Matrix error body:
            # {"errcode":"M_LIMIT_EXCEEDED","error":"Too Many Requests","retry_after_ms":2000}
            return {
                "errcode": "M_LIMIT_EXCEEDED",
                "error": "Too Many Requests",
                "retry_after_ms": 2000,
                "status": 429,
            }
        self.send_log.append(payload)
        return {"event_id": self._evt_id()}

    def force_disconnect(self) -> None:
        self._disconnect_pending = True

    def pop_disconnect(self) -> bool:
        was = self._disconnect_pending
        self._disconnect_pending = False
        return was
