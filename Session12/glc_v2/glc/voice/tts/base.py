"""TTS provider ABC + canonical result/error types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SynthesizeResult:
    audio_b64: str
    mime: str
    sample_rate: int
    provider: str
    cost_usd: float = 0.0


class TTSError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class TTSProvider(ABC):
    name: str = ""

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}

    @abstractmethod
    async def synthesize(self, text: str, voice_id: str | None = None) -> SynthesizeResult:
        """Return a SynthesizeResult with `provider` set to `self.name`."""
        raise NotImplementedError
