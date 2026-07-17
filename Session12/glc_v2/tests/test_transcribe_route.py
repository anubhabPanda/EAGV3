"""POST /v1/transcribe route — request validation and provider routing.

The route delegates to the STT dispatcher in glc.voice.stt.router;
tests inject fake providers via `register_test_provider` rather than
patching upstream HTTP calls.
"""

from __future__ import annotations

import base64

import pytest

from glc.voice.stt.base import STTError, STTProvider, TranscribeResult
from glc.voice.stt.router import register_test_provider


def _fake_provider(name: str, *, text: str = "hello", raise_: STTError | None = None) -> STTProvider:
    class Fake(STTProvider):
        async def transcribe(self, audio, mime):
            if raise_ is not None:
                raise raise_
            return TranscribeResult(text=text, language="en", duration_ms=10, provider=name, cost_usd=0.0)

    Fake.name = name
    return Fake()


@pytest.fixture(autouse=True)
def _clean_providers():
    yield
    for n in ("groq_whisper", "whisper_cpp", "gemini_live"):
        register_test_provider(n, None)


def test_transcribe_streaming_returns_400(app_client):
    body = {"audio_b64": base64.b64encode(b"\x00\x00").decode(), "mime": "audio/wav", "prefer": "streaming"}
    r = app_client.post("/v1/transcribe", json=body)
    assert r.status_code == 400


def test_transcribe_bad_base64_returns_400(app_client):
    r = app_client.post("/v1/transcribe", json={"audio_b64": "!!!not-base64!!!", "mime": "audio/wav"})
    assert r.status_code in (400, 502)


def test_transcribe_default_calls_registered_provider(app_client):
    register_test_provider("groq_whisper", _fake_provider("groq_whisper"))
    body = {"audio_b64": base64.b64encode(b"\x00" * 100).decode(), "mime": "audio/wav", "prefer": "default"}
    r = app_client.post("/v1/transcribe", json=body)
    assert r.status_code == 200
    j = r.json()
    assert j["text"] == "hello"
    assert j["provider"] == "groq_whisper"


def test_transcribe_provider_error_becomes_502(app_client):
    register_test_provider(
        "groq_whisper",
        _fake_provider("groq_whisper", raise_=STTError("groq HTTP 500: upstream is down")),
    )
    body = {"audio_b64": base64.b64encode(b"\x00").decode(), "mime": "audio/wav", "prefer": "default"}
    r = app_client.post("/v1/transcribe", json=body)
    assert r.status_code == 502


def test_transcribe_stub_returns_501(app_client):
    """No provider registered — the catalogue stub raises
    NotImplementedError, dispatcher converts to status=501."""
    body = {"audio_b64": base64.b64encode(b"\x00").decode(), "mime": "audio/wav", "prefer": "default"}
    r = app_client.post("/v1/transcribe", json=body)
    assert r.status_code == 501
