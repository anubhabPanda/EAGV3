"""Response format mapping and normalization helper for the Groq Whisper STT provider."""

from __future__ import annotations

from glc.voice.stt.base import TranscribeResult
from glc.voice.stt.providers.groq_whisper.schemas import GroqVerboseJsonResponse

# Mapping of common language names to ISO 639-1 language codes
LANG_NAME_TO_CODE = {
    "english": "en",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "italian": "it",
    "japanese": "ja",
    "chinese": "zh",
    "portuguese": "pt",
    "russian": "ru",
    "korean": "ko",
}


def convert_response(parsed: GroqVerboseJsonResponse, provider_name: str) -> TranscribeResult:
    """Normalize language identifiers, calculate duration in ms, and build TranscribeResult."""
    duration_sec = parsed.duration or 0.0
    duration_ms = int(duration_sec * 1000)

    raw_lang = (parsed.language or "en").lower()
    lang = LANG_NAME_TO_CODE.get(raw_lang, raw_lang)

    return TranscribeResult(
        text=parsed.text,
        language=lang,
        duration_ms=duration_ms,
        provider=provider_name,
        cost_usd=0.0,
    )
