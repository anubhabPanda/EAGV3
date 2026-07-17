"""Groq Whisper Large v3 Turbo STT provider tests.

Six structural tests + one behavioural test. The structural tests
assert the canonical TranscribeResult contract holds; the behavioural
test asserts the channel-specific wire behaviour from the upstream
docs at https://console.groq.com/docs/speech-text.
"""

from __future__ import annotations

import pytest

from glc.voice.stt.base import STTError, TranscribeResult
from glc.voice.stt.providers.groq_whisper.adapter import Provider
from tests.voice.stt.mocks.groq_whisper_mock import GroqWhisperMock


@pytest.fixture
def mock():
    return GroqWhisperMock()


# ── Structural tests ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_provider_name_matches(mock):
    adapter = Provider(config={"mock": mock})
    assert adapter.name == "groq_whisper"


@pytest.mark.asyncio
async def test_transcribe_returns_transcribe_result(mock):
    adapter = Provider(config={"mock": mock})
    r = await adapter.transcribe(b"AUDIO", "audio/wav")
    assert isinstance(r, TranscribeResult)
    assert r.provider == "groq_whisper"
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
async def test_channel_specific_behaviour_openai_multipart_shape(mock):
    """The Groq endpoint is OpenAI-compatible. The adapter must POST
    multipart/form-data with `file` (audio bytes) and `model`. Adapters
    that send JSON, or omit the model field, get a 400 from Groq."""
    mock.canned_transcribe_text = "groq output"
    mock.canned_model = "whisper-large-v3-turbo"
    adapter = Provider(config={"mock": mock})
    r = await adapter.transcribe(b"AUDIO BYTES", "audio/wav")
    assert r.text == "groq output"
    assert mock.last_model == "whisper-large-v3-turbo"
    assert mock.last_response_format == "verbose_json"
    assert mock.received_multipart is not None
