"""Mock-API fake for the ElevenLabs Flash v2.5 TTS provider.

Wire-format source: https://elevenlabs.io/docs/api-reference/text-to-speech
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from glc.voice.tts.base import SynthesizeResult, TTSError


@dataclass
class ElevenlabsMock:
    canned_audio_b64: str = "QUFBQQ=="  # base64("AAAA")
    canned_mime: str = "audio/wav"
    canned_sample_rate: int = 24000
    received_calls: list[dict[str, Any]] = field(default_factory=list)
    rate_limited: bool = False
    upstream_failure: tuple[int, str] | None = None
    monthly_chars_used: int = 0
    monthly_chars_limit: int = 10_000
    last_body: dict | None = None

    async def synthesize(self, text: str, voice_id: str | None = None) -> SynthesizeResult:
        self.received_calls.append({"text_len": len(text), "voice_id": voice_id})
        if self.rate_limited:
            raise TTSError("upstream rate-limited", status=429)
        if self.upstream_failure is not None:
            status, msg = self.upstream_failure
            raise TTSError(msg, status=status)
        self.last_body = {"text": text, "voice_id": voice_id}
        self.monthly_chars_used += len(text)
        return SynthesizeResult(
            audio_b64=self.canned_audio_b64,
            mime=self.canned_mime,
            sample_rate=self.canned_sample_rate,
            provider="elevenlabs",
            cost_usd=0.0,
        )

    def record_frame(self, frame: dict[str, Any]) -> None:
        if hasattr(self, "frames_sent"):
            self.frames_sent.append(frame)
            setup = frame.get("setup")
            if isinstance(setup, dict):
                gc = setup.get("generationConfig") or setup.get("generation_config") or {}
                mods = gc.get("responseModalities") or gc.get("response_modalities")
                if mods is not None:
                    self.setup_response_modalities = list(mods)
