"""Mock-API fake for Twilio Programmable Voice + Media Streams.

Wire-format source:
  https://www.twilio.com/docs/voice/twiml
  https://www.twilio.com/docs/voice/twiml/stream
  https://www.twilio.com/docs/voice/twiml/connect

Inbound has two shapes:
  1. Call webhook — form-urlencoded with `CallSid`, `From`, `To`,
     `Direction`, `CallStatus`. The adapter responds with TwiML XML.
  2. Media Streams WebSocket frames — JSON `{event:"media",
     media:{payload}}` where payload is base64-encoded mu-law audio
     at 8 kHz mono.

Outbound: TwiML XML body from the webhook response, OR `messages.send`
on the Media Streams WS for outbound audio chunks (out of scope here).

Helpers
-------
queue_owner_message(text)         → inbound CALL webhook from owner
queue_stranger_message(text)      → inbound CALL webhook from stranger
queue_media_frame(audio_bytes)    → WS media frame with base64 audio
transcribe(audio_bytes)           → synthetic STT for the media test
store_artifact(sha, data)         → artifact handle
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any

OWNER_PHONE = "+19999999999"
STRANGER_PHONE = "+17777777777"
OWNER_ID = OWNER_PHONE
STRANGER_ID = STRANGER_PHONE

BOT_PHONE = "+15555550100"
CALL_SID = "CA0000000000000000000000000000abcd"
STREAM_SID = "MZ0000000000000000000000000000beef"


def _call_form(*, from_phone: str, call_sid: str = CALL_SID) -> dict[str, Any]:
    return {
        "CallSid": call_sid,
        "AccountSid": "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "From": from_phone,
        "To": BOT_PHONE,
        "FromCountry": "US",
        "Direction": "inbound",
        "CallStatus": "ringing",
        "CallerName": "owner" if from_phone == OWNER_PHONE else "stranger",
    }


def _media_frame(*, audio_bytes: bytes, stream_sid: str = STREAM_SID, chunk: int = 1) -> dict[str, Any]:
    return {
        "event": "media",
        "sequenceNumber": str(chunk),
        "streamSid": stream_sid,
        "media": {
            "track": "inbound",
            "chunk": str(chunk),
            "timestamp": str(chunk * 20),
            "payload": base64.b64encode(audio_bytes).decode(),
        },
    }


@dataclass
class TwilioVoiceMock:
    inbound_events: list[dict[str, Any]] = field(default_factory=list)
    send_log: list[dict[str, Any]] = field(default_factory=list)
    artifact_store: dict[str, bytes] = field(default_factory=dict)
    rate_limited: bool = False
    _disconnect_pending: bool = False
    _chunk: int = 0
    transcription_text: str = "hello from the phone"

    def queue_owner_message(self, text: str = "ringing") -> dict[str, Any]:
        # `text` is unused at the wire level — phone webhooks carry no
        # body. The kwarg stays for structural-test compatibility.
        ev = _call_form(from_phone=OWNER_PHONE)
        ev["_synthetic_call_label"] = text
        self.inbound_events.append(ev)
        return ev

    def queue_stranger_message(self, text: str = "ringing") -> dict[str, Any]:
        ev = _call_form(from_phone=STRANGER_PHONE)
        ev["_synthetic_call_label"] = text
        self.inbound_events.append(ev)
        return ev

    def queue_media_frame(self, audio_bytes: bytes = b"\xff\x7f" * 80) -> dict[str, Any]:
        self._chunk += 1
        ev = _media_frame(audio_bytes=audio_bytes, chunk=self._chunk)
        self.inbound_events.append(ev)
        return ev

    def transcribe(self, audio_bytes: bytes) -> str:
        # The real adapter calls /v1/transcribe; the mock returns a
        # canned transcript so the test stays offline.
        return self.transcription_text

    def store_artifact(self, sha: str, data: bytes) -> str:
        self.artifact_store[sha] = data
        return f"art:{sha}"

    async def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.rate_limited:
            return {"code": 20429, "message": "Too Many Requests", "status": 429}
        self.send_log.append(payload)
        return {"status": 200, "sid": STREAM_SID}

    def force_disconnect(self) -> None:
        self._disconnect_pending = True

    def pop_disconnect(self) -> bool:
        was = self._disconnect_pending
        self._disconnect_pending = False
        return was
