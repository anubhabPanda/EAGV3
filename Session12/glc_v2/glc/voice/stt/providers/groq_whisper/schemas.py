"""Channel-specific Pydantic types for the Groq Whisper provider.

Canonical TranscribeResult lives in glc.voice.stt.base.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GroqSegment(BaseModel):
    """Represents an individual audio segment in the Groq response."""

    id: int | None = None
    seek: int | None = None
    start: float | None = None
    end: float | None = None
    text: str | None = None
    tokens: list[int] | None = None
    temperature: float | None = None
    avg_logprob: float | None = None
    compression_ratio: float | None = None
    no_speech_prob: float | None = None


class GroqVerboseJsonResponse(BaseModel):
    """Represents the complete verbose_json response structure from Groq."""

    text: str
    language: str | None = "en"
    duration: float | None = 0.0
    segments: list[GroqSegment] = Field(default_factory=list)
