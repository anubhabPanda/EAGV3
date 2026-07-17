"""TTS dispatcher.

`prefer="default"` -> kokoro (local, free, ~300MB)
`prefer="quality"` -> elevenlabs (free tier, 10k chars/month)
`prefer="streaming"` -> cartesia (sub-50ms TTFA)
`prefer="realtime"` -> gemini_live (full-duplex)
`prefer="fallback"` -> system_fallback (always works; `say` on macOS,
                                       pyttsx3 elsewhere)

system_fallback ships fully implemented so a fresh install can answer
/v1/speak?prefer=fallback on day one. The other four are stubs until
their owning groups land an implementation.
"""

from __future__ import annotations

import importlib

from glc.voice.tts.base import SynthesizeResult, TTSError, TTSProvider

PREFER_TO_PROVIDER: dict[str, str] = {
    "default": "kokoro",
    "quality": "elevenlabs",
    "streaming": "cartesia",
    "realtime": "gemini_live",
    "fallback": "system_fallback",
}

PROVIDERS_PACKAGE = "glc.voice.tts.providers"

_TEST_PROVIDERS: dict[str, TTSProvider] = {}


def _load_provider(name: str) -> TTSProvider:
    if name in _TEST_PROVIDERS:
        return _TEST_PROVIDERS[name]
    try:
        mod = importlib.import_module(f"{PROVIDERS_PACKAGE}.{name}.adapter")
    except ImportError as e:
        raise TTSError(f"TTS provider '{name}' is not installed. ({e})") from e
    cls = getattr(mod, "Provider", None)
    if cls is None or not issubclass(cls, TTSProvider):
        raise TTSError(
            f"TTS provider '{name}' does not expose a Provider(TTSProvider). "
            "Group assignment: implement on adapter.py."
        )
    return cls()


async def synthesize(text: str, voice_id: str | None = None, prefer: str = "default") -> SynthesizeResult:
    if prefer not in PREFER_TO_PROVIDER:
        raise TTSError(f"unknown prefer={prefer!r}. Pick one of: {list(PREFER_TO_PROVIDER)}")
    name = PREFER_TO_PROVIDER[prefer]
    provider = _load_provider(name)
    try:
        return await provider.synthesize(text, voice_id)
    except NotImplementedError as e:
        raise TTSError(
            f"TTS provider '{name}' is a stub (group assignment not yet merged). "
            f"Try `prefer=fallback` for the always-on system TTS. ({e})",
            status=501,
        ) from e


def register_test_provider(name: str, provider: TTSProvider | None) -> None:
    if provider is None:
        _TEST_PROVIDERS.pop(name, None)
    else:
        _TEST_PROVIDERS[name] = provider


# Back-compat shims for monkeypatching from older tests.
async def _call_kokoro(text: str, voice_id: str | None) -> SynthesizeResult:  # pragma: no cover
    return await _load_provider("kokoro").synthesize(text, voice_id)


async def _call_elevenlabs(text: str, voice_id: str | None) -> SynthesizeResult:  # pragma: no cover
    return await _load_provider("elevenlabs").synthesize(text, voice_id)


async def _call_cartesia(text: str, voice_id: str | None) -> SynthesizeResult:  # pragma: no cover
    return await _load_provider("cartesia").synthesize(text, voice_id)


def _call_system_tts(text: str) -> SynthesizeResult:  # pragma: no cover
    import asyncio

    return asyncio.get_event_loop().run_until_complete(
        _load_provider("system_fallback").synthesize(text, None)
    )


__all__ = [
    "PREFER_TO_PROVIDER",
    "SynthesizeResult",
    "TTSError",
    "TTSProvider",
    "register_test_provider",
    "synthesize",
]
