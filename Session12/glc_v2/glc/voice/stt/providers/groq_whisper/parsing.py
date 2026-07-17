"""Response validation and JSON parsing for the Groq Whisper STT provider."""

from __future__ import annotations

import json

import httpx

from glc.voice.stt.base import STTError
from glc.voice.stt.providers.groq_whisper.schemas import GroqVerboseJsonResponse


def validate_and_parse_response(response: httpx.Response) -> GroqVerboseJsonResponse:
    """Validate HTTP code, parse JSON and validate schema using Pydantic."""
    if response.status_code != 200:
        raise STTError(
            f"Groq API returned error {response.status_code}: {response.text}",
            status=response.status_code,
        )

    try:
        res_json = response.json()
    except json.JSONDecodeError as e:
        raise STTError(f"Malformed JSON response from Groq: {e}", status=502) from e

    try:
        return GroqVerboseJsonResponse.model_validate(res_json)
    except Exception as e:
        raise STTError(f"Unexpected response schema from Groq: {e}", status=502) from e
