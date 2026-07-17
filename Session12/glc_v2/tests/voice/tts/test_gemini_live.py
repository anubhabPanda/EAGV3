"""Gemini Live TTS (BidiGenerateContent WebSocket) TTS provider tests.

Six structural tests + one behavioural test (response_modalities_audio).
Wire-format source: https://ai.google.dev/api/multimodal-live.
"""

from __future__ import annotations

import pytest

from glc.voice.tts.base import SynthesizeResult, TTSError
from glc.voice.tts.providers.gemini_live.adapter import Provider
from tests.voice.tts.mocks.gemini_live_mock import GeminiLiveMock


@pytest.fixture
def mock():
    return GeminiLiveMock()


@pytest.mark.asyncio
async def test_provider_name_matches(mock):
    adapter = Provider(config={"mock": mock})
    assert adapter.name == "gemini_live"


@pytest.mark.asyncio
async def test_synthesize_returns_synthesize_result(mock):
    adapter = Provider(config={"mock": mock})
    r = await adapter.synthesize("hello", voice_id="default")
    assert isinstance(r, SynthesizeResult)
    assert r.provider == "gemini_live"
    assert r.audio_b64
    assert r.sample_rate > 0


@pytest.mark.asyncio
async def test_synthesize_passes_text_to_upstream(mock):
    adapter = Provider(config={"mock": mock})
    await adapter.synthesize("hello world", voice_id="x")
    assert mock.received_calls
    assert mock.received_calls[-1]["text_len"] == len("hello world")


@pytest.mark.asyncio
async def test_synthesize_records_sample_rate(mock):
    mock.canned_sample_rate = 22050
    adapter = Provider(config={"mock": mock})
    r = await adapter.synthesize("hi")
    assert r.sample_rate == 22050


@pytest.mark.asyncio
async def test_synthesize_propagates_upstream_error(mock):
    mock.upstream_failure = (502, "upstream broken")
    adapter = Provider(config={"mock": mock})
    with pytest.raises(TTSError) as ei:
        await adapter.synthesize("hi")
    assert ei.value.status == 502


@pytest.mark.asyncio
async def test_synthesize_handles_empty_text(mock):
    adapter = Provider(config={"mock": mock})
    r = await adapter.synthesize("", voice_id=None)
    assert isinstance(r, SynthesizeResult)


@pytest.mark.asyncio
async def test_channel_specific_behaviour_response_modalities_audio(mock):
    """The BidiGenerateContentSetup frame's `responseModalities` field
    controls whether the server emits audio or text. Defaulting to
    text means the adapter silently produces no audio for every
    synthesis call. The adapter must explicitly set
    `responseModalities: ["AUDIO"]`."""
    adapter = Provider(config={"mock": mock})
    await adapter.synthesize("hello", voice_id=None)
    assert mock.setup_response_modalities == ["AUDIO"], (
        f"setup frame must declare responseModalities=['AUDIO']; got {mock.setup_response_modalities!r}"
    )
