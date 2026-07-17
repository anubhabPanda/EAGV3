"""STT facade. The dispatcher in `router.py` routes by `prefer=...` to
the provider catalogue under `providers/<name>/`."""

from glc.voice.stt.base import STTError, STTProvider, TranscribeResult
from glc.voice.stt.router import transcribe

__all__ = ["STTError", "STTProvider", "TranscribeResult", "transcribe"]
