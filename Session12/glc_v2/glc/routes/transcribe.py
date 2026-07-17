"""POST /v1/transcribe — STT through the voice routing layer."""

from __future__ import annotations

import base64
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from glc.config import get_or_create_install_token
from glc.voice.stt import STTError, transcribe

router = APIRouter()


def _require_token(authorization: str | None = Header(default=None)) -> None:
    """Verify install token for STT requests (mitigates A1)."""
    expected = get_or_create_install_token()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token (Authorization: Bearer <install_token>)")
    presented = authorization.removeprefix("Bearer ").strip()
    if presented != expected:
        raise HTTPException(403, "install token mismatch")


class TranscribeRequest(BaseModel):
    audio_b64: str
    mime: str = "audio/wav"
    agent: str | None = None
    prefer: Literal["default", "local", "streaming"] = "default"


class TranscribeResponse(BaseModel):
    text: str
    language: str
    duration_ms: int
    provider: str
    cost_usd: float = Field(default=0.0)


@router.post("/v1/transcribe", response_model=TranscribeResponse)
async def transcribe_route(req: TranscribeRequest, _auth: None = Depends(_require_token)):
    try:
        audio = base64.b64decode(req.audio_b64)
    except Exception as e:
        raise HTTPException(400, f"audio_b64 is not valid base64: {e}") from e
    try:
        r = await transcribe(audio, req.mime, prefer=req.prefer)
    except STTError as e:
        if req.prefer == "streaming":
            raise HTTPException(400, str(e)) from e
        raise HTTPException(e.status or 502, str(e)) from e
    return TranscribeResponse(
        text=r.text,
        language=r.language,
        duration_ms=r.duration_ms,
        provider=r.provider,
        cost_usd=r.cost_usd,
    )
