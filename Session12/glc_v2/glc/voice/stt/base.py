"""STT provider ABC + canonical result/error types.

Every provider under `glc/voice/stt/providers/<name>/adapter.py`
subclasses `STTProvider` and implements `transcribe(audio, mime)`.
The result shape is the same across providers so callers don't
notice which one ran.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class TranscribeResult:
    text: str
    language: str
    duration_ms: int
    provider: str
    cost_usd: float = 0.0


class STTError(Exception):
    """Raised on provider failure. Wraps upstream status code if known."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class STTProvider(ABC):
    name: str = ""

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}

    @abstractmethod
    async def transcribe(self, audio: bytes, mime: str) -> TranscribeResult:
        """Return a TranscribeResult with `provider` set to `self.name`."""
        raise NotImplementedError
