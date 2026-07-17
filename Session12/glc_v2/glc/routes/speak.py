"""POST /v1/speak — TTS through the voice routing layer."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from glc.config import get_or_create_install_token
from glc.voice.tts import TTSError, synthesize

router = APIRouter()


def _require_token(authorization: str | None = Header(default=None)) -> None:
    """Verify install token for TTS requests (mitigates A1)."""
    expected = get_or_create_install_token()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token (Authorization: Bearer <install_token>)")
    presented = authorization.removeprefix("Bearer ").strip()
    if presented != expected:
        raise HTTPException(403, "install token mismatch")


class SpeakRequest(BaseModel):
    text: str
    voice_id: str | None = None
    agent: str | None = None
    prefer: Literal["default", "quality", "streaming", "realtime", "fallback"] = "default"


class SpeakResponse(BaseModel):
    audio_b64: str
    mime: str
    sample_rate: int
    provider: str
    cost_usd: float = 0.0


@router.post("/v1/speak", response_model=SpeakResponse)
async def speak_route(req: SpeakRequest, _auth: None = Depends(_require_token)):
    try:
        r = await synthesize(req.text, voice_id=req.voice_id, prefer=req.prefer)
    except TTSError as e:
        raise HTTPException(e.status or 502, str(e)) from e
    return SpeakResponse(
        audio_b64=r.audio_b64,
        mime=r.mime,
        sample_rate=r.sample_rate,
        provider=r.provider,
        cost_usd=r.cost_usd,
    )
