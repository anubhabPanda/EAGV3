"""STT / TTS dispatcher tests — provider catalogue lookup, prefer
routing, and fail-fast on stub providers.

The shipped provider catalogue is stub-only for STT and 4-of-5 stubs
for TTS (system_fallback ships working). Tests inject fakes through
`register_test_provider` so they run offline.
"""

from __future__ import annotations

import pytest

from glc.voice.stt import STTError, transcribe
from glc.voice.stt.base import STTProvider, TranscribeResult
from glc.voice.stt.router import register_test_provider as register_stt
from glc.voice.tts import SynthesizeResult, TTSError, synthesize
from glc.voice.tts.base import TTSProvider
from glc.voice.tts.router import register_test_provider as register_tts


def _make_stt(name: str, text: str = "hello") -> STTProvider:
    class Fake(STTProvider):
        async def transcribe(self, audio, mime):
            return TranscribeResult(text=text, language="en", duration_ms=100, provider=name, cost_usd=0.0)

    Fake.name = name
    return Fake()


def _make_tts(name: str, audio_b64: str = "AAAA") -> TTSProvider:
    class Fake(TTSProvider):
        async def synthesize(self, text, voice_id=None):
            return SynthesizeResult(
                audio_b64=audio_b64, mime="audio/wav", sample_rate=24000, provider=name, cost_usd=0.0
            )

    Fake.name = name
    return Fake()


@pytest.fixture(autouse=True)
def _clean_test_providers():
    yield
    for n in ("groq_whisper", "whisper_cpp", "gemini_live"):
        register_stt(n, None)
    for n in ("kokoro", "elevenlabs", "cartesia", "gemini_live", "system_fallback"):
        register_tts(n, None)


# ── STT ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_transcribe_streaming_raises_with_guidance():
    """Without a gemini_live provider registered, streaming returns a
    clear pointer at the WebSocket S12 deliverable."""
    with pytest.raises(STTError) as ei:
        await transcribe(b"\x00\x00", "audio/wav", prefer="streaming")
    msg = str(ei.value).lower()
    assert "websocket" in msg or "gemini live" in msg


@pytest.mark.asyncio
async def test_transcribe_default_routes_to_groq_whisper():
    register_stt("groq_whisper", _make_stt("groq_whisper", "hello world"))
    r = await transcribe(b"\x00" * 10, "audio/wav", prefer="default")
    assert r.text == "hello world"
    assert r.provider == "groq_whisper"


@pytest.mark.asyncio
async def test_transcribe_local_routes_to_whisper_cpp():
    register_stt("whisper_cpp", _make_stt("whisper_cpp", "local"))
    r = await transcribe(b"\x00", "audio/wav", prefer="local")
    assert r.provider == "whisper_cpp"


@pytest.mark.asyncio
async def test_transcribe_default_when_stub_returns_501():
    # No provider registered -> the catalogue stub raises NotImplementedError
    # which the dispatcher translates into an STTError(status=501).
    with pytest.raises(STTError) as ei:
        await transcribe(b"\x00", "audio/wav", prefer="default")
    assert ei.value.status == 501


@pytest.mark.asyncio
async def test_transcribe_unknown_prefer_errors():
    with pytest.raises(STTError):
        await transcribe(b"", "audio/wav", prefer="ultraseaweed")


# ── TTS ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_synthesize_default_routes_to_kokoro():
    register_tts("kokoro", _make_tts("kokoro", "K"))
    r = await synthesize("hi", prefer="default")
    assert r.provider == "kokoro"


@pytest.mark.asyncio
async def test_synthesize_quality_routes_to_elevenlabs():
    register_tts("elevenlabs", _make_tts("elevenlabs", "E"))
    r = await synthesize("hi", prefer="quality")
    assert r.provider == "elevenlabs"


@pytest.mark.asyncio
async def test_synthesize_streaming_routes_to_cartesia():
    register_tts("cartesia", _make_tts("cartesia", "C"))
    r = await synthesize("hi", prefer="streaming")
    assert r.provider == "cartesia"


@pytest.mark.asyncio
async def test_synthesize_realtime_routes_to_gemini_live():
    register_tts("gemini_live", _make_tts("gemini_live", "G"))
    r = await synthesize("hi", prefer="realtime")
    assert r.provider == "gemini_live"


def _can_use_system_tts() -> bool:
    import platform
    import shutil

    if platform.system() == "Darwin" and shutil.which("say"):
        return True
    try:
        import pyttsx3  # noqa: F401

        return True
    except Exception:
        return False


@pytest.mark.asyncio
@pytest.mark.skipif(
    not _can_use_system_tts(),
    reason="system_fallback needs macOS `say` or pyttsx3 — Linux CI runner without pyttsx3 cannot exercise it",
)
async def test_synthesize_fallback_ships_working():
    """system_fallback is the one TTS provider that is implemented in
    the shipped scaffold — `prefer=fallback` must produce audio."""
    r = await synthesize("glc fallback test", prefer="fallback")
    assert r.provider == "system_fallback"
    assert len(r.audio_b64) > 100


@pytest.mark.asyncio
async def test_synthesize_unknown_prefer_errors():
    with pytest.raises(TTSError):
        await synthesize("hi", prefer="nope")


@pytest.mark.asyncio
async def test_synthesize_default_when_stub_returns_501():
    with pytest.raises(TTSError) as ei:
        await synthesize("hi", prefer="default")
    assert ei.value.status == 501
