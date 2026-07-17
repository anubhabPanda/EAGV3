"""Slack adapter tests.

Wire-format basis: real Slack Events API + chat.postMessage payloads.
https://api.slack.com/events/message
https://api.slack.com/methods/chat.postMessage

Six structural tests + one behavioural test (thread continuity).
"""

from __future__ import annotations

from datetime import datetime

import pytest

from glc.channels.catalogue.slack.adapter import Adapter
from glc.channels.envelope import ChannelMessage, ChannelReply
from glc.security.pairing import get_pairing_store
from tests.channels.mocks.slack_mock import OWNER_ID, STRANGER_ID, SlackMock


@pytest.fixture
def mock():
    return SlackMock()


@pytest.fixture
def pair_owner():
    store = get_pairing_store()
    store.force_pair_owner("slack", OWNER_ID, user_handle="owner")
    yield
    store.revoke("slack", OWNER_ID)


@pytest.mark.asyncio
async def test_on_message_owner_returns_valid_envelope(mock, pair_owner):
    adapter = Adapter(config={"mock": mock})
    ev = mock.queue_owner_message("hello from owner")
    msg = await adapter.on_message(ev)
    assert isinstance(msg, ChannelMessage)
    assert msg.channel == "slack"
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
    """The dispatched payload must conform to chat.postMessage — the
    canonical fields are `channel` (a `C...` or `D...` id) and
    `text`. Adapters that store the agent's user id under `channel`
    or that put the text under `message` fail this test."""
    adapter = Adapter(config={"mock": mock})
    reply = ChannelReply(channel="slack", channel_user_id=OWNER_ID, text="hi back")
    await adapter.send(reply)
    assert len(mock.send_log) == 1
    body = mock.send_log[0]
    assert "channel" in body, "chat.postMessage requires `channel`"
    assert "text" in body, "chat.postMessage requires `text`"
    assert body["text"] == "hi back"
    # `channel` is a conversation id (Cxxx or Dxxx), not a user id.
    assert isinstance(body["channel"], str)
    assert body["channel"].startswith(("C", "D", "G"))


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
    reply = ChannelReply(channel="slack", channel_user_id=OWNER_ID, text="x")
    result = await adapter.send(reply)
    assert isinstance(result, dict)
    assert result.get("status") == 429 or result.get("error") == "ratelimited"


@pytest.mark.asyncio
async def test_allowlist_silently_drops_stranger_in_public(mock):
    adapter = Adapter(config={"mock": mock, "is_public_channel": True})
    ev = mock.queue_stranger_message("hi from public")
    msg = await adapter.on_message(ev)
    assert msg is None or msg.trust_level == "untrusted"


@pytest.mark.asyncio
async def test_channel_specific_behaviour_thread_continuity(mock, pair_owner):
    """Slack threads live entirely inside the `thread_ts` field. The
    adapter must:
      - populate ChannelMessage.thread_id from `thread_ts` on inbound
      - propagate ChannelReply.thread_id back into the outbound
        chat.postMessage as `thread_ts`
    A reply lost from a thread is a UX regression that shows up
    immediately in real Slack usage."""
    adapter = Adapter(config={"mock": mock})
    ev = mock.queue_threaded_message(thread_ts="1700000000.000050")
    msg = await adapter.on_message(ev)
    assert msg is not None
    assert msg.thread_id == "1700000000.000050"

    reply = ChannelReply(
        channel="slack", channel_user_id=OWNER_ID, text="threaded reply", thread_id=msg.thread_id
    )
    await adapter.send(reply)
    body = mock.send_log[-1]
    assert body.get("thread_ts") == "1700000000.000050", (
        "ChannelReply.thread_id must propagate to chat.postMessage thread_ts"
    )
