"""Twilio Voice adapter tests.

Wire-format basis: Twilio Programmable Voice TwiML + Media Streams.
https://www.twilio.com/docs/voice/twiml
https://www.twilio.com/docs/voice/twiml/stream

Six structural tests + one behavioural test (TwiML on call-in,
media-stream frame → ChannelMessage with voice_audio_ref).
"""

from __future__ import annotations

import re
from datetime import datetime

import pytest

from glc.channels.catalogue.twilio_voice.adapter import Adapter
from glc.channels.envelope import ChannelMessage, ChannelReply
from glc.security.pairing import get_pairing_store
from tests.channels.mocks.twilio_voice_mock import (
    OWNER_ID,
    STRANGER_ID,
    TwilioVoiceMock,
)


@pytest.fixture
def mock():
    return TwilioVoiceMock()


@pytest.fixture
def pair_owner():
    store = get_pairing_store()
    store.force_pair_owner("twilio_voice", OWNER_ID, user_handle="owner")
    yield
    store.revoke("twilio_voice", OWNER_ID)


@pytest.mark.asyncio
async def test_on_message_owner_returns_valid_envelope(mock, pair_owner):
    adapter = Adapter(config={"mock": mock})
    ev = mock.queue_owner_message("ringing")
    msg = await adapter.on_message(ev)
    assert isinstance(msg, ChannelMessage)
    assert msg.channel == "twilio_voice"
    assert msg.channel_user_id == OWNER_ID
    assert msg.trust_level == "owner_paired"
    assert isinstance(msg.arrived_at, datetime)


@pytest.mark.asyncio
async def test_on_message_stranger_is_untrusted(mock):
    adapter = Adapter(config={"mock": mock})
    ev = mock.queue_stranger_message("ringing")
    msg = await adapter.on_message(ev)
    assert msg is not None
    assert msg.channel_user_id == STRANGER_ID
    assert msg.trust_level == "untrusted"


@pytest.mark.asyncio
async def test_send_emits_valid_wire_payload(mock, pair_owner):
    """Outbound voice replies become TwiML XML the webhook returns.
    The body must include `<Response>` and a `<Say>` or `<Connect>`
    element."""
    adapter = Adapter(config={"mock": mock})
    reply = ChannelReply(channel="twilio_voice", channel_user_id=OWNER_ID, text="hi back")
    await adapter.send(reply)
    assert len(mock.send_log) == 1
    body = mock.send_log[0]
    twiml = body.get("twiml") if isinstance(body, dict) else body
    assert twiml is not None
    assert "<Response>" in twiml
    assert ("<Say>" in twiml and "hi back" in twiml) or "<Connect>" in twiml


@pytest.mark.asyncio
async def test_disconnect_is_handled(mock, pair_owner):
    adapter = Adapter(config={"mock": mock})
    mock.force_disconnect()
    try:
        await adapter.on_message(mock.queue_owner_message("ringing"))
    except Exception as e:
        pytest.fail(f"adapter did not handle disconnect cleanly: {e!r}")


@pytest.mark.asyncio
async def test_rate_limit_propagates_429(mock, pair_owner):
    mock.rate_limited = True
    adapter = Adapter(config={"mock": mock})
    reply = ChannelReply(channel="twilio_voice", channel_user_id=OWNER_ID, text="x")
    result = await adapter.send(reply)
    assert isinstance(result, dict)
    assert result.get("status") == 429 or result.get("code") == 20429


@pytest.mark.asyncio
async def test_allowlist_silently_drops_stranger_in_public(mock):
    adapter = Adapter(config={"mock": mock, "is_public_channel": True})
    ev = mock.queue_stranger_message("ringing")
    msg = await adapter.on_message(ev)
    assert msg is None or msg.trust_level == "untrusted"


@pytest.mark.asyncio
async def test_channel_specific_behaviour_call_to_twiml_then_media(mock, pair_owner):
    """The voice flow is two-step:
      1. Call webhook → adapter returns TwiML opening a Media Stream
         back to the GLC voice WebSocket.
      2. Media-stream frame → adapter decodes base64 mu-law audio,
         transcribes via `mock.transcribe(bytes)`, persists the bytes
         to the artifact store, and surfaces a ChannelMessage with
         `voice_audio_ref` set to the artifact handle and `text` set
         to the transcript.
    Adapters that drop step 2 cannot ever hear the caller speak."""
    adapter = Adapter(config={"mock": mock})

    # Step 1: incoming call should produce TwiML with a <Stream> element.
    ev = mock.queue_owner_message("ringing")
    await adapter.on_message(ev)
    # The adapter may emit a "call started" envelope here OR open the
    # TwiML response side-channel via send_log — accept either.
    reply = ChannelReply(channel="twilio_voice", channel_user_id=OWNER_ID, text="hi caller")
    await adapter.send(reply)
    twiml = mock.send_log[-1].get("twiml") if isinstance(mock.send_log[-1], dict) else mock.send_log[-1]
    assert twiml and re.search(r"<(Connect|Start)>\s*<Stream", twiml or ""), (
        "outbound TwiML must open a <Stream> for the Media Streams WS"
    )

    # Step 2: media frame arrives, must be transcribed and turned into
    # a ChannelMessage with voice_audio_ref.
    frame = mock.queue_media_frame(audio_bytes=b"\xff\x7f" * 100)
    msg2 = await adapter.on_message(frame)
    assert msg2 is not None
    assert msg2.voice_audio_ref is not None
    assert msg2.voice_audio_ref.startswith("art:"), (
        "voice_audio_ref must encode an artifact handle, not the raw bytes"
    )
    assert msg2.text == mock.transcription_text
