"""Channel-specific Pydantic types for the ElevenLabs TTS provider."""

from __future__ import annotations

from pydantic import BaseModel


class ElevenLabsVoiceSettings(BaseModel):
    stability: float = 0.5
    similarity_boost: float = 0.75
    style: float = 0.0
    speed: float = 1.0
    use_speaker_boost: bool = True


class ElevenLabsRequest(BaseModel):
    text: str
    model_id: str = "eleven_flash_v2_5"
    voice_settings: ElevenLabsVoiceSettings | None = None
