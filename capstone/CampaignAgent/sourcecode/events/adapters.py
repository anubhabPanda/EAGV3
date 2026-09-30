"""Thin normalizers. Transport-specific code ends at EventEnvelope."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import Any

from .models import EventEnvelope


def cron_event(schedule_id: str, *, occurred_at: datetime | None = None,
               data: dict[str, Any] | None = None) -> EventEnvelope:
    instant = occurred_at or datetime.now(UTC)
    return EventEnvelope(id=f"{schedule_id}:{instant.isoformat()}", source=f"cron.{schedule_id}",
                         type="schedule.tick", subject=schedule_id, occurred_at=instant, data=data or {})


def webhook_event(*, source: str, delivery_id: str, event_type: str,
                  payload: dict[str, Any], occurred_at: datetime | None = None) -> EventEnvelope:
    return EventEnvelope(id=delivery_id, source=source, type=event_type,
                         occurred_at=occurred_at or datetime.now(UTC), data=payload)


def gmail_pubsub_event(message: dict[str, Any]) -> EventEnvelope:
    """Normalize Google's Pub/Sub push wrapper; fetching mail remains a tool decision."""
    wrapped = message.get("message")
    if not isinstance(wrapped, dict) or not isinstance(wrapped.get("data"), str):
        raise ValueError("Gmail Pub/Sub push needs message.data")
    try:
        payload = json.loads(base64.b64decode(wrapped["data"], validate=True))
    except Exception as error:
        raise ValueError("Gmail Pub/Sub message.data is not valid base64 JSON") from error
    if not isinstance(payload, dict) or not payload.get("emailAddress") or not payload.get("historyId"):
        raise ValueError("Gmail notification needs emailAddress and historyId")
    published = wrapped.get("publishTime")
    occurred = datetime.fromisoformat(str(published).replace("Z", "+00:00")) if published else datetime.now(UTC)
    return EventEnvelope(id=str(wrapped.get("messageId") or f"gmail-{payload['historyId']}"),
                         source="gmail.pubsub", type="gmail.history.changed",
                         subject=str(payload["emailAddress"]), occurred_at=occurred, data=payload)
