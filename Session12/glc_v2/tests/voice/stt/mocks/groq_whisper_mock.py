"""Mock-API fake for the Groq Whisper Large v3 Turbo STT provider.

Wire-format source: https://console.groq.com/docs/speech-text

Adapter authors call this fake instead of the real upstream when
`config["mock"]` is set. Tests inspect `received_calls` and the
mock-specific capture fields to assert the adapter dispatched the
right shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from glc.voice.stt.base import STTError, TranscribeResult


@dataclass
class GroqWhisperMock:
    canned_transcribe_text: str = "hello"
    canned_language: str = "en"
    canned_duration_ms: int = 200
    canned_model: str = "model-name"
    received_calls: list[dict[str, Any]] = field(default_factory=list)
    rate_limited: bool = False
    upstream_failure: tuple[int, str] | None = None
    model_path: str = "/fake/ggml-base.bin"
    received_multipart: dict | None = None  # last multipart form
    last_model: str | None = None
    last_response_format: str | None = None

    async def transcribe(self, audio: bytes, mime: str) -> TranscribeResult:
        self.received_calls.append({"audio_len": len(audio), "mime": mime})
        if self.rate_limited:
            raise STTError("upstream rate-limited", status=429)
        if self.upstream_failure is not None:
            status, msg = self.upstream_failure
            raise STTError(msg, status=status)
        self.received_multipart = {"file_bytes": audio, "mime": mime}
        self.last_model = self.canned_model
        self.last_response_format = "verbose_json"
        return TranscribeResult(
            text=self.canned_transcribe_text,
            language=self.canned_language,
            duration_ms=self.canned_duration_ms,
            provider="groq_whisper",
            cost_usd=0.0,
        )

    def record_frame(self, frame: dict[str, Any]) -> None:
        """Generic WebSocket-style frame recorder. Used by gemini_live."""
        if hasattr(self, "frames_sent"):
            self.frames_sent.append(frame)
            if self.setup_frame is None and ("setup" in frame or frame.get("type") == "setup"):
                self.setup_frame = frame
