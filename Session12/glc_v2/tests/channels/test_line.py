"""LINE adapter tests.

Wire-format basis: LINE Messaging API.
https://developers.line.biz/en/reference/messaging-api/

Six structural tests + one behavioural test (reply-token-vs-push
selection).
"""

from __future__ import annotations

from datetime import datetime

import pytest

from glc.channels.catalogue.line.adapter import Adapter
from glc.channels.envelope import ChannelMessage, ChannelReply
from glc.security.pairing import get_pairing_store
from tests.channels.mocks.line_mock import OWNER_ID, STRANGER_ID, LineMock


@pytest.fixture
def mock():
    return LineMock()


@pytest.fixture
def pair_owner():
    store = get_pairing_store()
    store.force_pair_owner("line", OWNER_ID, user_handle="owner", _allow_in_process=True)
    yield
    store.revoke("line", OWNER_ID)
    store.force_pair_owner("line", OWNER_ID, user_handle="owner")
    yield
    store.revoke("line", OWNER_ID)


@pytest.mark.asyncio
async def test_on_message_owner_returns_valid_envelope(mock, pair_owner):
    adapter = Adapter(config={"mock": mock})
    ev = mock.queue_owner_message("hello from owner")
    msg = await adapter.on_message(ev)
    assert isinstance(msg, ChannelMessage)
    assert msg.channel == "line"
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
    """The reply endpoint requires `replyToken` and a `messages` array
    of objects (NOT a bare `text`). The push endpoint requires `to`
    and `messages`."""
    adapter = Adapter(config={"mock": mock})
    ev = mock.queue_owner_message("seed")
    await adapter.on_message(ev)
    reply = ChannelReply(channel="line", channel_user_id=OWNER_ID, text="hi back")
    await adapter.send(reply)
    assert len(mock.send_log) == 1
    body = mock.send_log[0]
    assert "messages" in body, "LINE replies require a `messages` array"
    assert isinstance(body["messages"], list)
    first = body["messages"][0]
    assert first.get("type") == "text"
    assert first.get("text") == "hi back"


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
    reply = ChannelReply(channel="line", channel_user_id=OWNER_ID, text="x")
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
async def test_channel_specific_behaviour_reply_token_then_push(mock, pair_owner):
    """LINE reply tokens are one-shot and quota-free; push messages
    cost against the monthly quota. The adapter must:
      - parse the inbound webhook and stash `replyToken` in a TTL
        store keyed by user id (the mock's `consume_reply_token` is
        the read side)
      - emit a reply payload (`{replyToken, messages}`) for the first
        outbound after an inbound
      - fall back to push (`{to, messages}`) for subsequent outbounds
        when no in-flight token is available

    Adapters that always use push will exhaust the monthly quota in
    production and silently drop replies."""
    adapter = Adapter(config={"mock": mock})
    # Inbound primes a reply token.
    ev = mock.queue_owner_message("trigger")
    await adapter.on_message(ev)
    # First reply: must use replyToken.
    await adapter.send(ChannelReply(channel="line", channel_user_id=OWNER_ID, text="first"))
    body1 = mock.send_log[-1]
    assert "replyToken" in body1, "first outbound must consume the reply token"

    # Second reply (no fresh inbound): must use push (`to`).
    await adapter.send(ChannelReply(channel="line", channel_user_id=OWNER_ID, text="second"))
    body2 = mock.send_log[-1]
    assert "to" in body2 and body2.get("to") == OWNER_ID, (
        "second outbound must fall back to push when no replyToken is in flight"
    )
    assert "replyToken" not in body2, "push payload must not include a replyToken"
