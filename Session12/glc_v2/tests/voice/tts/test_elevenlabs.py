"""ElevenLabs Flash v2.5 TTS provider tests.

Six structural tests + one behavioural test (free_tier_quota_tracking).
Wire-format source: https://elevenlabs.io/docs/api-reference/text-to-speech.
"""

from __future__ import annotations

import pytest

from glc.voice.tts.base import SynthesizeResult, TTSError
from glc.voice.tts.providers.elevenlabs.adapter import Provider
from tests.voice.tts.mocks.elevenlabs_mock import ElevenlabsMock


@pytest.fixture
def mock():
    return ElevenlabsMock()


@pytest.mark.asyncio
async def test_provider_name_matches(mock):
    adapter = Provider(config={"mock": mock})
    assert adapter.name == "elevenlabs"


@pytest.mark.asyncio
async def test_synthesize_returns_synthesize_result(mock):
    adapter = Provider(config={"mock": mock})
    r = await adapter.synthesize("hello", voice_id="default")
    assert isinstance(r, SynthesizeResult)
    assert r.provider == "elevenlabs"
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
async def test_channel_specific_behaviour_free_tier_quota_tracking(mock):
    """ElevenLabs free tier caps at 10,000 characters per month. The
    adapter must track cumulative usage and fail-fast with a
    structured error before sending the request when the quota is
    spent. Adapters that ignore the quota waste a round-trip and
    return ElevenLabs's 401-style error body."""
    mock.monthly_chars_used = 9_990
    mock.monthly_chars_limit = 10_000
    adapter = Provider(config={"mock": mock})
    with pytest.raises(TTSError) as ei:
        await adapter.synthesize("this is a long enough message to bust the cap", voice_id="rachel")
    assert ei.value.status == 429
    assert "quota" in str(ei.value).lower() or "limit" in str(ei.value).lower()
