"""Groq Whisper Large v3 Turbo Speech-to-Text provider adapter.

Connects to the Groq Cloud STT API by orchestrating logical operations
defined in modular helper modules.
"""

from __future__ import annotations

from glc.voice.stt.base import STTProvider, TranscribeResult
from glc.voice.stt.providers.groq_whisper.config import load_config
from glc.voice.stt.providers.groq_whisper.conversion import convert_response
from glc.voice.stt.providers.groq_whisper.network import execute_request
from glc.voice.stt.providers.groq_whisper.parsing import validate_and_parse_response
from glc.voice.stt.providers.groq_whisper.payload import build_payload
from glc.voice.stt.providers.groq_whisper.validation import validate_input


class Provider(STTProvider):
    """Groq Whisper Speech-to-Text provider implementation."""

    name = "groq_whisper"

    async def transcribe(self, audio: bytes, mime: str) -> TranscribeResult:
        """Transcribe audio bytes using the Groq Whisper API by orchestrating helpers.

        If a mock is provided in the configuration, delegates directly
        to the mock provider.
        """
        # Test Mock Delegation
        mock_provider = self.config.get("mock")
        if mock_provider is not None:
            return await mock_provider.transcribe(audio, mime)

        # Validate input types
        validate_input(audio, mime)

        # Return empty result immediately for empty audio
        if len(audio) == 0:
            return TranscribeResult(
                text="",
                language="en",
                duration_ms=0,
                provider=self.name,
                cost_usd=0.0,
            )

        # Load API key and target model from environment or config
        api_key, model = load_config(self.config)

        # Build files and data multipart payload
        files, data = build_payload(audio, mime, model)

        # Execute HTTP POST request asynchronously
        response = await execute_request(api_key, files, data)

        # Validate response status, parse JSON and validate schema
        parsed_response = validate_and_parse_response(response)

        # Normalize duration and language, returning TranscribeResult
        return convert_response(parsed_response, self.name)
