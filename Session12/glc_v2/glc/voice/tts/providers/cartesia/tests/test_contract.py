"""Provider-local contract tests for the Cartesia TTS implementation.

These tests live beside the adapter and schemas so the Cartesia group can
validate its own boundary without changing the shared top-level test suite.
"""

from __future__ import annotations

import base64

import pytest

from glc.voice.tts.base import SynthesizeResult, TTSError
from glc.voice.tts.providers.cartesia.adapter import Provider
from glc.voice.tts.providers.cartesia.schemas import (
    CARTESIA_API_VERSION,
    CARTESIA_ENDPOINT,
    DEFAULT_MODEL_ID,
    DEFAULT_SAMPLE_RATE,
    OUTPUT_CONTAINER,
    OUTPUT_ENCODING,
)


@pytest.mark.asyncio
async def test_synthesize_empty_text_short_circuits_before_api_key(monkeypatch):
    """Protect the cheap no-op path from doing credential or network work.

    Empty text should produce an empty successful result even when live Cartesia
    credentials are absent, because there is nothing useful to synthesize.
    """
    monkeypatch.delenv("CARTESIA_API_KEY", raising=False)

    result = await Provider().synthesize("")

    assert result == SynthesizeResult(
        audio_b64="",
        mime="audio/wav",
        sample_rate=24000,
        provider="cartesia",
        cost_usd=0.0,
    )


@pytest.mark.asyncio
async def test_synthesize_missing_api_key_raises_tts_error(monkeypatch):
    """Make the live-path credential failure explicit at the provider boundary.

    Non-empty synthesis without an injected mock must fail before any outbound
    request when CARTESIA_API_KEY is absent.
    """
    monkeypatch.delenv("CARTESIA_API_KEY", raising=False)

    with pytest.raises(TTSError) as exc:
        await Provider().synthesize("hello")

    assert exc.value.status == 500
    assert "CARTESIA_API_KEY" in str(exc.value)


@pytest.mark.asyncio
async def test_synthesize_live_path_streams_and_encodes_audio(monkeypatch):
    """Exercise the live adapter boundary with a fake streaming client.

    The adapter should stream response chunks, accumulate complete audio for
    SynthesizeResult, and send schema-built headers/body without touching the
    real Cartesia network.
    """
    from glc.voice.tts.providers.cartesia import adapter as adapter_module

    class FakeResponse:
        """Provide the subset of httpx.Response used by the stream path.

        The fake yields two chunks so the test proves chunk accumulation rather
        than a single pre-buffered response body.
        """

        is_error = False
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def aiter_bytes(self):
            yield b"WA"
            yield b"V"

    class FakeClient:
        """Record the outbound request while returning a streaming response.

        This keeps the assertion at the provider boundary: method, endpoint,
        headers, JSON body, and encoded result are all validated together.
        """

        is_closed = False

        def __init__(self):
            self.calls = []

        def stream(self, method, url, *, headers, json):
            self.calls.append(
                {
                    "method": method,
                    "url": url,
                    "headers": headers,
                    "json": json,
                }
            )
            return FakeResponse()

    fake_client = FakeClient()
    voice_id = "a0e99841-438c-4a64-b679-ae501e7d6091"
    monkeypatch.setenv("CARTESIA_API_KEY", "test-key")
    monkeypatch.setenv("CARTESIA_VOICE_ID", "env-voice")
    monkeypatch.setattr(adapter_module, "_CLIENT", fake_client, raising=False)

    result = await Provider().synthesize("hello", voice_id=voice_id)

    assert result.audio_b64 == base64.b64encode(b"WAV").decode("ascii")
    assert result.mime == "audio/wav"
    assert result.sample_rate == DEFAULT_SAMPLE_RATE
    assert result.provider == "cartesia"
    assert fake_client.calls == [
        {
            "method": "POST",
            "url": CARTESIA_ENDPOINT,
            "headers": {
                "X-API-Key": "test-key",
                "Cartesia-Version": CARTESIA_API_VERSION,
                "Content-Type": "application/json",
            },
            "json": {
                "transcript": "hello",
                "voice": {"mode": "id", "id": voice_id},
                "model_id": DEFAULT_MODEL_ID,
                "output_format": {
                    "container": OUTPUT_CONTAINER,
                    "encoding": OUTPUT_ENCODING,
                    "sample_rate": DEFAULT_SAMPLE_RATE,
                },
            },
        }
    ]
