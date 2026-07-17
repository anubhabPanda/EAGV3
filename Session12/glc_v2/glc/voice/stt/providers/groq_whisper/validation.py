"""Input validation for the Groq Whisper Speech-to-Text provider."""

from __future__ import annotations

from glc.voice.stt.base import STTError


def validate_input(audio: bytes, mime: str) -> None:
    """Validate that the audio bytes and MIME type are of correct types."""
    if not isinstance(audio, bytes):
        raise STTError("audio must be of type bytes", status=400)
    if not mime or not isinstance(mime, str):
        raise STTError("MIME type must be a non-empty string", status=400)
