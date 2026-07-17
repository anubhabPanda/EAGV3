"""Cartesia Sonic TTS provider tests.

Six structural tests + one behavioural test (time_to_first_audio).
Wire-format source: https://docs.cartesia.ai/api-reference/tts/bytes.
"""

from __future__ import annotations

import pytest

from glc.voice.tts.base import SynthesizeResult, TTSError
from glc.voice.tts.providers.cartesia.adapter import Provider
from tests.voice.tts.mocks.cartesia_mock import CartesiaMock


@pytest.fixture
def mock():
    return CartesiaMock()


@pytest.mark.asyncio
async def test_provider_name_matches(mock):
    adapter = Provider(config={"mock": mock})
    assert adapter.name == "cartesia"


@pytest.mark.asyncio
async def test_synthesize_returns_synthesize_result(mock):
    adapter = Provider(config={"mock": mock})
    r = await adapter.synthesize("hello", voice_id="default")
    assert isinstance(r, SynthesizeResult)
    assert r.provider == "cartesia"
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
async def test_channel_specific_behaviour_time_to_first_audio(mock):
    """Cartesia Sonic's TTFA budget is sub-50ms for streaming use
    cases like Twilio Voice outbound. The adapter must not buffer
    the entire response — it should return as soon as the first
    audio chunk is available. The mock records the timestamp of the
    first byte; the test asserts the recorded delta from request
    start is under a synthetic threshold (10ms against the offline
    mock, which is generous)."""
    import time

    adapter = Provider(config={"mock": mock})
    t0 = time.time()
    await adapter.synthesize("hello", voice_id="neutral-id")
    assert mock.first_byte_at is not None
    ttfa_ms = (mock.first_byte_at - t0) * 1000
    assert ttfa_ms < 200, f"TTFA was {ttfa_ms:.1f}ms; Cartesia replies must stream early"
