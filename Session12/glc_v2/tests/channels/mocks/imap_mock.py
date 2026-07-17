"""Mock-API fake for generic IMAP/SMTP.

Wire-format source:
  https://datatracker.ietf.org/doc/html/rfc5322 (Internet Message Format)
  https://datatracker.ietf.org/doc/html/rfc2045 (MIME multipart)
  https://datatracker.ietf.org/doc/html/rfc9051 (IMAP4rev2 FETCH)

Inbound: raw RFC 822 message bytes — IMAP FETCH returns the literal
message body. The adapter parses it via stdlib `email`.
Outbound: SMTP envelope shape `{from, to, raw}` where `raw` is the
message bytes produced by `email.message.EmailMessage.as_bytes()`.

Helpers
-------
queue_owner_message(text)              → text-only RFC 822 from owner
queue_stranger_message(text)           → text-only RFC 822 from stranger
queue_pdf_attachment_message(text)     → multipart/mixed with a
                                         text/plain part and a
                                         base64-encoded PDF attachment
"""

from __future__ import annotations

from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Any

OWNER_EMAIL = "owner@example.com"
STRANGER_EMAIL = "stranger@example.com"
OWNER_ID = OWNER_EMAIL
STRANGER_ID = STRANGER_EMAIL

BOT_EMAIL = "bot@example.com"

# A minimal but real-looking PDF byte string. The %PDF- magic header
# is what mime detection routines key on.
PDF_BYTES = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _text_message(*, from_addr: str, subject: str, body: str, uid: int) -> dict[str, Any]:
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = BOT_EMAIL
    msg["Subject"] = subject
    msg["Date"] = "Wed, 17 Jun 2026 12:00:00 +0000"
    msg["Message-ID"] = f"<{uid}@example.com>"
    msg.set_content(body)
    return {"uid": uid, "raw": bytes(msg)}


def _pdf_attachment_message(*, from_addr: str, body: str, uid: int) -> dict[str, Any]:
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = BOT_EMAIL
    msg["Subject"] = "report attached"
    msg["Date"] = "Wed, 17 Jun 2026 12:00:00 +0000"
    msg["Message-ID"] = f"<{uid}@example.com>"
    msg.set_content(body)
    msg.add_attachment(PDF_BYTES, maintype="application", subtype="pdf", filename="report.pdf")
    return {"uid": uid, "raw": bytes(msg)}


@dataclass
class ImapMock:
    inbound_events: list[dict[str, Any]] = field(default_factory=list)
    send_log: list[dict[str, Any]] = field(default_factory=list)
    artifact_store: dict[str, bytes] = field(default_factory=dict)
    rate_limited: bool = False
    _disconnect_pending: bool = False
    _next_uid: int = 100

    def _uid(self) -> int:
        self._next_uid += 1
        return self._next_uid

    def queue_owner_message(self, text: str = "hello") -> dict[str, Any]:
        ev = _text_message(from_addr=OWNER_EMAIL, subject="ping", body=text, uid=self._uid())
        self.inbound_events.append(ev)
        return ev

    def queue_stranger_message(self, text: str = "ping") -> dict[str, Any]:
        ev = _text_message(from_addr=STRANGER_EMAIL, subject="ping", body=text, uid=self._uid())
        self.inbound_events.append(ev)
        return ev

    def queue_pdf_attachment_message(self, body: str = "see attached") -> dict[str, Any]:
        ev = _pdf_attachment_message(from_addr=OWNER_EMAIL, body=body, uid=self._uid())
        self.inbound_events.append(ev)
        return ev

    def store_artifact(self, sha: str, data: bytes) -> str:
        """The adapter persists attachment bytes here. Returns the
        canonical `art:<sha>` handle the envelope's Attachment.ref
        should encode."""
        self.artifact_store[sha] = data
        return f"art:{sha}"

    async def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.rate_limited:
            # smtplib raises smtplib.SMTPResponseException on 4xx/5xx.
            return {"status": 421, "error": "Service not available, try later"}
        self.send_log.append(payload)
        return {"status": 250, "id": f"smtp-{len(self.send_log)}"}

    def force_disconnect(self) -> None:
        self._disconnect_pending = True

    def pop_disconnect(self) -> bool:
        was = self._disconnect_pending
        self._disconnect_pending = False
        return was
