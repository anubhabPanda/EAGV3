"""Mock-API fake for the System TTS fallback (shipped working) TTS provider.

Wire-format source: macOS `say` / pyttsx3
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from glc.voice.tts.base import SynthesizeResult, TTSError


@dataclass
class SystemFallbackMock:
    canned_audio_b64: str = "QUFBQQ=="  # base64("AAAA")
    canned_mime: str = "audio/wav"
    canned_sample_rate: int = 24000
    received_calls: list[dict[str, Any]] = field(default_factory=list)
    rate_limited: bool = False
    upstream_failure: tuple[int, str] | None = None

    async def synthesize(self, text: str, voice_id: str | None = None) -> SynthesizeResult:
        self.received_calls.append({"text_len": len(text), "voice_id": voice_id})
        if self.rate_limited:
            raise TTSError("upstream rate-limited", status=429)
        if self.upstream_failure is not None:
            status, msg = self.upstream_failure
            raise TTSError(msg, status=status)

        return SynthesizeResult(
            audio_b64=self.canned_audio_b64,
            mime=self.canned_mime,
            sample_rate=self.canned_sample_rate,
            provider="system_fallback",
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
