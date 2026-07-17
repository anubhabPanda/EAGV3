"""Multipart form-data payload builder for the Groq Whisper STT provider."""

from __future__ import annotations

RESPONSE_FORMAT = "verbose_json"


def build_payload(audio: bytes, mime: str, model: str) -> tuple[dict, dict]:
    """Map MIME type to extension and build multipart dictionary payloads."""
    ext = "wav"
    if "mpeg" in mime or "mp3" in mime:
        ext = "mp3"
    elif "ogg" in mime:
        ext = "ogg"
    elif "webm" in mime:
        ext = "webm"
    elif "flac" in mime:
        ext = "flac"
    elif "mp4" in mime:
        ext = "mp4"
    elif "m4a" in mime:
        ext = "m4a"

    files = {
        "file": (f"audio.{ext}", audio, mime),
    }
    data = {
        "model": model,
        "response_format": RESPONSE_FORMAT,
    }
    return files, data
