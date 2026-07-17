"""Gemini Live (BidiGenerateContent WebSocket) STT provider tests.

Six structural tests + one behavioural test. The structural tests
assert the canonical TranscribeResult contract holds; the behavioural
test asserts the channel-specific wire behaviour from the upstream
docs at https://ai.google.dev/api/multimodal-live.
"""

from __future__ import annotations

import pytest

from glc.voice.stt.base import STTError, TranscribeResult
from glc.voice.stt.providers.gemini_live.adapter import Provider
from tests.voice.stt.mocks.gemini_live_mock import GeminiLiveMock


@pytest.fixture
def mock():
    return GeminiLiveMock()


# ── Structural tests ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_provider_name_matches(mock):
    adapter = Provider(config={"mock": mock})
    assert adapter.name == "gemini_live"


@pytest.mark.asyncio
async def test_transcribe_returns_transcribe_result(mock):
    adapter = Provider(config={"mock": mock})
    r = await adapter.transcribe(b"AUDIO", "audio/wav")
    assert isinstance(r, TranscribeResult)
    assert r.provider == "gemini_live"
    assert r.language == "en"


@pytest.mark.asyncio
async def test_transcribe_passes_audio_to_upstream(mock):
    adapter = Provider(config={"mock": mock})
    await adapter.transcribe(b"X" * 1234, "audio/wav")
    assert mock.received_calls, "adapter must invoke the upstream at least once"
    assert mock.received_calls[-1]["audio_len"] == 1234


@pytest.mark.asyncio
async def test_transcribe_records_duration_ms(mock):
    mock.canned_duration_ms = 1337
    adapter = Provider(config={"mock": mock})
    r = await adapter.transcribe(b"AUDIO", "audio/wav")
    assert r.duration_ms == 1337


@pytest.mark.asyncio
async def test_transcribe_propagates_upstream_error(mock):
    mock.upstream_failure = (500, "upstream is down")
    adapter = Provider(config={"mock": mock})
    with pytest.raises(STTError) as ei:
        await adapter.transcribe(b"AUDIO", "audio/wav")
    assert ei.value.status == 500


@pytest.mark.asyncio
async def test_transcribe_handles_empty_audio(mock):
    adapter = Provider(config={"mock": mock})
    r = await adapter.transcribe(b"", "audio/wav")
    assert isinstance(r, TranscribeResult)
    # Empty audio is allowed; the provider may return empty text without
    # erroring (Groq, Whisper, and Gemini Live all do this in practice).


# ── Channel-specific behavioural test ──────────────────────────────


@pytest.mark.asyncio
async def test_channel_specific_behaviour_setup_frame_first(mock):
    """The Live API rejects sessions where audio arrives before the
    BidiGenerateContentSetup frame. The adapter must send setup as
    the first frame and only then push the audio payload."""
    adapter = Provider(config={"mock": mock})
    await adapter.transcribe(b"audio", "audio/pcm")
    assert mock.frames_sent, "adapter must have sent at least one frame"
    first = mock.frames_sent[0]
    assert "setup" in first or first.get("type") == "setup", f"first frame must be setup, got: {first}"
