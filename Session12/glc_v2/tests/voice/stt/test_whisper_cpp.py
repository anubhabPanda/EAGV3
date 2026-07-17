"""whisper.cpp (local subprocess) STT provider tests.

Six structural tests + one behavioural test. The structural tests
assert the canonical TranscribeResult contract holds; the behavioural
test asserts the channel-specific wire behaviour from the upstream
docs at https://github.com/ggerganov/whisper.cpp.
"""

from __future__ import annotations

import pytest

from glc.voice.stt.base import STTError, TranscribeResult
from glc.voice.stt.providers.whisper_cpp.adapter import Provider
from tests.voice.stt.mocks.whisper_cpp_mock import WhisperCppMock


@pytest.fixture
def mock():
    return WhisperCppMock()


# ── Structural tests ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_provider_name_matches(mock):
    adapter = Provider(config={"mock": mock})
    assert adapter.name == "whisper_cpp"


@pytest.mark.asyncio
async def test_transcribe_returns_transcribe_result(mock):
    adapter = Provider(config={"mock": mock})
    r = await adapter.transcribe(b"AUDIO", "audio/wav")
    assert isinstance(r, TranscribeResult)
    assert r.provider == "whisper_cpp"
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
async def test_channel_specific_behaviour_vad_skips_silent_input(mock):
    """Invoking whisper-cli on silence wastes hundreds of milliseconds
    of subprocess startup with no transcript to show. The adapter
    must VAD-detect silence (zero-amplitude bytes) and short-circuit
    before launching the subprocess."""
    adapter = Provider(config={"mock": mock})
    silent = b"\x00" * 16000  # 1s of pure silence
    r = await adapter.transcribe(silent, "audio/wav")
    assert r.text == ""
    assert mock.subprocess_call_count == 0, "subprocess must not run on silent input"
