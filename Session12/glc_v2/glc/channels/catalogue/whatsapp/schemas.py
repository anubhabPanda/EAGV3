"""Channel-specific Pydantic types for the whatsapp adapter."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MetaParsed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_id: str
    text: str | None
    message_id: str
    timestamp: str
    profile_name: str | None


class TwilioParsed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_id: str
    text: str | None
    message_id: str | None
    timestamp: datetime
    profile_name: str | None


class MetaSendText(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str


class MetaSendPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messaging_product: str = "whatsapp"
    to: str
    type: str = "text"
    text: MetaSendText


class TwilioSendPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    To: str
    From: str
    Body: str
