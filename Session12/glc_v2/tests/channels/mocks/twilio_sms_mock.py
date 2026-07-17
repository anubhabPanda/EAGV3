"""Mock-API fake for Twilio SMS (and MMS).

Wire-format source:
  https://www.twilio.com/docs/messaging/guides/webhook-request
  https://www.twilio.com/docs/messaging/api/message-resource#create-a-message-resource

Inbound: a webhook POST with `application/x-www-form-urlencoded` body
(NOT JSON). Twilio sends `From`, `To`, `Body`, `MessageSid`,
`AccountSid`, plus `NumMedia` and `MediaUrl0..N` for MMS.
Outbound: a `messages.create` POST with form fields `From`, `To`,
`Body`, plus optional `MediaUrl` for image attachments.

Helpers
-------
queue_owner_message(text)              → text SMS from owner
queue_stranger_message(text)           → text SMS from stranger
queue_mms_message(text, media_url)     → MMS with NumMedia=1 and
                                         MediaUrl0
download(url)                          → returns synthetic image bytes
                                         registered against the URL
store_artifact(sha, data)              → artifact handle
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

OWNER_PHONE = "+19999999999"
STRANGER_PHONE = "+17777777777"
OWNER_ID = OWNER_PHONE
STRANGER_ID = STRANGER_PHONE

BOT_PHONE = "+15555550100"


def _sms_form(*, from_phone: str, body: str, message_sid: str = "SM01") -> dict[str, Any]:
    return {
        "MessageSid": message_sid,
        "AccountSid": "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "From": from_phone,
        "To": BOT_PHONE,
        "Body": body,
        "NumMedia": "0",
        "FromCountry": "US",
        "FromZip": "94105",
        "FromCity": "SAN FRANCISCO",
        "FromState": "CA",
    }


def _mms_form(
    *,
    from_phone: str,
    body: str,
    media_url: str,
    media_content_type: str = "image/jpeg",
    message_sid: str = "MM01",
) -> dict[str, Any]:
    form = _sms_form(from_phone=from_phone, body=body, message_sid=message_sid)
    form.update(
        {
            "NumMedia": "1",
            "MediaUrl0": media_url,
            "MediaContentType0": media_content_type,
        }
    )
    return form


@dataclass
class TwilioSmsMock:
    inbound_events: list[dict[str, Any]] = field(default_factory=list)
    send_log: list[dict[str, Any]] = field(default_factory=list)
    artifact_store: dict[str, bytes] = field(default_factory=dict)
    media_store: dict[str, bytes] = field(default_factory=dict)
    rate_limited: bool = False
    _disconnect_pending: bool = False
    _next: int = 100

    def _id(self) -> str:
        self._next += 1
        return f"MM{self._next:032d}"

    def queue_owner_message(self, text: str = "hello") -> dict[str, Any]:
        ev = _sms_form(from_phone=OWNER_PHONE, body=text, message_sid=self._id())
        self.inbound_events.append(ev)
        return ev

    def queue_stranger_message(self, text: str = "ping") -> dict[str, Any]:
        ev = _sms_form(from_phone=STRANGER_PHONE, body=text, message_sid=self._id())
        self.inbound_events.append(ev)
        return ev

    def queue_mms_message(
        self,
        body: str = "see photo",
        media_url: str = "https://api.twilio.com/Media/IM01.jpg",
        media_bytes: bytes = b"\xff\xd8\xff synthetic jpeg",
    ) -> dict[str, Any]:
        self.media_store[media_url] = media_bytes
        ev = _mms_form(from_phone=OWNER_PHONE, body=body, media_url=media_url, message_sid=self._id())
        self.inbound_events.append(ev)
        return ev

    def download(self, url: str) -> bytes:
        if url not in self.media_store:
            raise KeyError(f"unknown media URL: {url}")
        return self.media_store[url]

    def store_artifact(self, sha: str, data: bytes) -> str:
        self.artifact_store[sha] = data
        return f"art:{sha}"

    async def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.rate_limited:
            # Real Twilio 429 (rate-limited) JSON body:
            return {
                "code": 20429,
                "message": "Too Many Requests",
                "more_info": "https://www.twilio.com/docs/errors/20429",
                "status": 429,
            }
        self.send_log.append(payload)
        return {
            "sid": self._id(),
            "status": "queued",
            "to": payload.get("To"),
            "from": payload.get("From"),
            "body": payload.get("Body", ""),
        }

    def force_disconnect(self) -> None:
        self._disconnect_pending = True

    def pop_disconnect(self) -> bool:
        was = self._disconnect_pending
        self._disconnect_pending = False
        return was
