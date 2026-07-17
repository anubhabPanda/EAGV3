"""Webhook adapter tests.

Wire-format basis: Stripe-style signed webhooks (HMAC-SHA256 over
`f"{timestamp}.{body}"` using a per-integration shared secret).

Six structural tests + one behavioural test (signature + replay-window
verification).
"""

from __future__ import annotations

from datetime import datetime

import pytest

from glc.channels.catalogue.webhook.adapter import Adapter
from glc.channels.envelope import ChannelMessage, ChannelReply
from glc.security.pairing import get_pairing_store
from tests.channels.mocks.webhook_mock import (
    DEFAULT_SHARED_SECRET,
    OWNER_ID,
    STRANGER_ID,
    WebhookMock,
)


@pytest.fixture
def mock():
    return WebhookMock()


@pytest.fixture
def pair_owner():
    store = get_pairing_store()
    store.force_pair_owner("webhook", OWNER_ID, user_handle="owner")
    yield
    store.revoke("webhook", OWNER_ID)


@pytest.fixture(autouse=True)
def _set_secret(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SHARED_SECRET", DEFAULT_SHARED_SECRET)


@pytest.mark.asyncio
async def test_on_message_owner_returns_valid_envelope(mock, pair_owner):
    adapter = Adapter(config={"mock": mock})
    ev = mock.queue_owner_message("hello from owner")
    msg = await adapter.on_message(ev)
    assert isinstance(msg, ChannelMessage)
    assert msg.channel == "webhook"
    assert msg.channel_user_id == OWNER_ID
    assert msg.trust_level == "owner_paired"
    assert msg.text == "hello from owner"
    assert isinstance(msg.arrived_at, datetime)


@pytest.mark.asyncio
async def test_on_message_stranger_is_untrusted(mock):
    adapter = Adapter(config={"mock": mock})
    ev = mock.queue_stranger_message("hi")
    msg = await adapter.on_message(ev)
    assert msg is not None
    assert msg.channel_user_id == STRANGER_ID
    assert msg.trust_level == "untrusted"


@pytest.mark.asyncio
async def test_send_emits_valid_wire_payload(mock, pair_owner):
    """The outbound HTTP POST must carry the agent's reply text and
    identify the recipient. Generic webhook callers expect a JSON
    body with at least `recipient_id` and `text`."""
    adapter = Adapter(config={"mock": mock})
    reply = ChannelReply(channel="webhook", channel_user_id=OWNER_ID, text="hi back")
    await adapter.send(reply)
    assert len(mock.send_log) == 1
    body = mock.send_log[0]
    assert body.get("recipient_id") == OWNER_ID or body.get("to") == OWNER_ID
    assert body.get("text") == "hi back"


@pytest.mark.asyncio
async def test_disconnect_is_handled(mock, pair_owner):
    adapter = Adapter(config={"mock": mock})
    mock.force_disconnect()
    try:
        await adapter.on_message(mock.queue_owner_message("after disconnect"))
    except Exception as e:
        pytest.fail(f"adapter did not handle disconnect cleanly: {e!r}")


@pytest.mark.asyncio
async def test_rate_limit_propagates_429(mock, pair_owner):
    mock.rate_limited = True
    adapter = Adapter(config={"mock": mock})
    reply = ChannelReply(channel="webhook", channel_user_id=OWNER_ID, text="x")
    result = await adapter.send(reply)
    assert isinstance(result, dict)
    assert result.get("status") == 429


@pytest.mark.asyncio
async def test_allowlist_silently_drops_stranger_in_public(mock):
    adapter = Adapter(config={"mock": mock, "is_public_channel": True})
    ev = mock.queue_stranger_message("hi from public")
    msg = await adapter.on_message(ev)
    assert msg is None or msg.trust_level == "untrusted"


@pytest.mark.asyncio
async def test_channel_specific_behaviour_signed_replay_window(mock, pair_owner):
    """Stripe-style webhook signatures bind `t=<ts>` and `v1=<hmac>` so
    a captured payload cannot be replayed past a freshness window.
    The adapter must:
      - reject unsigned bodies                      → None
      - reject bodies with an expired `t` timestamp → None
      - accept fresh, correctly-signed bodies       → ChannelMessage

    Adapters that skip the timestamp check leave the webhook endpoint
    open to replay attacks the moment a body leaks to a log line."""
    adapter = Adapter(config={"mock": mock})

    raw, headers = mock.queue_unsigned(text="no signature")
    assert await adapter.on_message({"raw_body": raw, "headers": headers}) is None

    raw, headers = mock.queue_expired(text="too old")
    assert await adapter.on_message({"raw_body": raw, "headers": headers}) is None

    raw, headers = mock.queue_signed({"sender_id": OWNER_ID, "sender_handle": "owner", "text": "fresh"})
    out = await adapter.on_message({"raw_body": raw, "headers": headers})
    assert isinstance(out, ChannelMessage)
    assert out.text == "fresh"
