"""Network dispatcher using httpx for the Groq Whisper STT provider."""

from __future__ import annotations

import httpx

from glc.voice.stt.base import STTError

GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
REQUEST_TIMEOUT_SECONDS = 30.0


async def execute_request(api_key: str, files: dict, data: dict) -> httpx.Response:
    """Send the multipart request to Groq using an asynchronous client."""
    headers = {
        "Authorization": f"Bearer {api_key}",
    }
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            return await client.post(GROQ_STT_URL, headers=headers, files=files, data=data)
    except httpx.TimeoutException as e:
        raise STTError(f"HTTP request to Groq timed out: {e}", status=504) from e
    except httpx.RequestError as e:
        raise STTError(f"Network error communicating with Groq: {e}", status=502) from e
