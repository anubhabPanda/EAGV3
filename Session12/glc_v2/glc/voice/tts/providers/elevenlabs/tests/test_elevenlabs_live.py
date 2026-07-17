"""Live ElevenLabs API integration test.

Hits the real ElevenLabs text-to-speech endpoint, so it is marked
``requires_live_api`` and skipped in CI (``-m "not requires_live_api"``).
Run it locally with a free-tier key:

    export ELEVENLABS_API_KEY=sk_...            # required
    export ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM  # optional (Rachel default)
    uv run pytest glc/voice/tts/providers/elevenlabs/tests/ -m requires_live_api -v

It lives inside the adapter's owned path (not tests/) so the PR-boundary
check accepts it; the repo's testpaths=["tests"] means it is only collected
when pytest is pointed at this file explicitly.
"""

from __future__ import annotations

import os

import pytest

from glc.voice.tts.base import SynthesizeResult
from glc.voice.tts.providers.elevenlabs.adapter import Provider

pytestmark = pytest.mark.skipif(
    not os.environ.get("ELEVENLABS_API_KEY"),
    reason="ELEVENLABS_API_KEY not set — live API test skipped",
)


@pytest.mark.requires_live_api
@pytest.mark.asyncio
async def test_live_synthesize() -> None:
    """Calls the real ElevenLabs API and expects decodable audio back."""
    provider = Provider()
    result = await provider.synthesize("Hello from the live API test.")
    assert isinstance(result, SynthesizeResult)
    assert result.provider == "elevenlabs"
    assert result.audio_b64
    assert result.sample_rate > 0
