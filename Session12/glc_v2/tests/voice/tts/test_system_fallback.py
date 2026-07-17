"""System TTS fallback tests.

system_fallback is the only TTS provider that ships fully implemented.
It is NOT a group-assignment slot — these tests exercise the real
macOS `say` / pyttsx3 provider directly and assert the always-on
contract: a fresh install can answer `/v1/speak?prefer=fallback` on
day one.
"""

from __future__ import annotations

import platform
import shutil

import pytest

from glc.voice.tts.base import SynthesizeResult, TTSError
from glc.voice.tts.providers.system_fallback.adapter import Provider


def _can_use_system_tts() -> bool:
    if platform.system() == "Darwin" and shutil.which("say"):
        return True
    try:
        import pyttsx3  # noqa: F401

        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _can_use_system_tts(),
    reason="system_fallback needs macOS `say` or pyttsx3",
)


@pytest.mark.asyncio
async def test_provider_name_matches():
    assert Provider().name == "system_fallback"


@pytest.mark.asyncio
async def test_synthesize_returns_synthesize_result():
    r = await Provider().synthesize("hello", voice_id=None)
    assert isinstance(r, SynthesizeResult)
    assert r.provider == "system_fallback"
    assert r.audio_b64
    assert r.sample_rate > 0


@pytest.mark.asyncio
async def test_synthesize_passes_text_to_upstream():
    short = await Provider().synthesize("hi")
    longer = await Provider().synthesize("hello world from glc")
    assert len(longer.audio_b64) >= len(short.audio_b64)


@pytest.mark.asyncio
async def test_synthesize_records_sample_rate():
    r = await Provider().synthesize("sample-rate check")
    assert r.sample_rate in (16000, 22050, 24000, 44100, 48000)


@pytest.mark.asyncio
async def test_synthesize_propagates_upstream_error(monkeypatch):
    """Force the no-backend path so the provider raises TTSError."""
    from glc.voice.tts.providers.system_fallback import adapter as sf

    monkeypatch.setattr(
        sf,
        "platform",
        type("P", (), {"system": staticmethod(lambda: "Linux")}),
    )
    monkeypatch.setattr(sf.shutil, "which", lambda _: None)

    def _fail_pyttsx3(_text):
        raise TTSError("simulated: pyttsx3 not installed")

    monkeypatch.setattr(Provider, "_pyttsx3", staticmethod(_fail_pyttsx3))
    with pytest.raises(TTSError):
        await Provider().synthesize("error path probe")


@pytest.mark.asyncio
async def test_synthesize_handles_empty_text():
    r = await Provider().synthesize("")
    assert isinstance(r, SynthesizeResult)


@pytest.mark.asyncio
async def test_channel_specific_behaviour_ships_working_without_mock():
    """The contract: this provider answers on a fresh install with no
    API keys, no model download, no mock injection."""
    r = await Provider().synthesize("glc system fallback smoke")
    assert r.provider == "system_fallback"
    assert len(r.audio_b64) > 100
    assert r.sample_rate > 0
