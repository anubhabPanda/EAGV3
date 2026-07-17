"""Signal adapter tests.

Wire-format basis: signal-cli JSON-RPC service.
https://github.com/AsamK/signal-cli/wiki/JSON-RPC-service

Six structural tests + one behavioural test (DM vs group dispatch
selection).
"""

from __future__ import annotations

from datetime import datetime

import pytest

from glc.channels.catalogue.signal.adapter import Adapter
from glc.channels.envelope import ChannelMessage, ChannelReply
from glc.security.pairing import get_pairing_store
from tests.channels.mocks.signal_mock import (
    GROUP_ID_B64,
    OWNER_ID,
    STRANGER_ID,
    SignalMock,
)


@pytest.fixture
def mock():
    return SignalMock()


@pytest.fixture
def pair_owner():
    store = get_pairing_store()
    store.force_pair_owner("signal", OWNER_ID, user_handle="owner")
    yield
    store.revoke("signal", OWNER_ID)


@pytest.mark.asyncio
async def test_on_message_owner_returns_valid_envelope(mock, pair_owner):
    adapter = Adapter(config={"mock": mock})
    ev = mock.queue_owner_message("hello from owner")
    msg = await adapter.on_message(ev)
    assert isinstance(msg, ChannelMessage)
    assert msg.channel == "signal"
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
    """JSON-RPC `send` shape: `{jsonrpc:"2.0", id, method:"send",
    params:{recipient|groupId, message}}`. Adapters that forget the
    `method` field or drop the `jsonrpc` version fail."""
    adapter = Adapter(config={"mock": mock})
    reply = ChannelReply(channel="signal", channel_user_id=OWNER_ID, text="hi back")
    await adapter.send(reply)
    assert len(mock.send_log) == 1
    body = mock.send_log[0]
    assert body.get("jsonrpc") == "2.0"
    assert body.get("method") == "send"
    params = body.get("params") or {}
    assert params.get("message") == "hi back"
    assert params.get("recipient") == OWNER_ID, "DM dispatch must set recipient"


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
    reply = ChannelReply(channel="signal", channel_user_id=OWNER_ID, text="x")
    result = await adapter.send(reply)
    assert isinstance(result, dict)
    assert result.get("status") == 429 or (result.get("error") or {}).get("code") == -32603


@pytest.mark.asyncio
async def test_allowlist_silently_drops_stranger_in_public(mock):
    adapter = Adapter(config={"mock": mock, "is_public_channel": True})
    ev = mock.queue_stranger_message("hi from public")
    msg = await adapter.on_message(ev)
    assert msg is None or msg.trust_level == "untrusted"


@pytest.mark.asyncio
async def test_channel_specific_behaviour_group_vs_dm_dispatch(mock, pair_owner):
    """Signal addresses groups by their base64 `groupId`, not by any
    member's phone number. The adapter must:
      - surface `groupInfo.groupId` in
        ChannelMessage.metadata['signal_group_id'] on inbound
      - dispatch group replies as `{params: {groupId, message}}`
        when ChannelReply.thread_id is set to the group id
      - dispatch DM replies as `{params: {recipient, message}}`
    Adapters that always set `recipient` send group messages only to
    a single phone number — the rest of the group never sees the
    reply."""
    adapter = Adapter(config={"mock": mock})
    # Inbound group message
    ev = mock.queue_group_message(text="ping", group_id=GROUP_ID_B64)
    msg = await adapter.on_message(ev)
    assert msg is not None
    assert msg.metadata.get("signal_group_id") == GROUP_ID_B64

    # Group reply: thread_id encodes the group id
    await adapter.send(
        ChannelReply(channel="signal", channel_user_id=OWNER_ID, text="group reply", thread_id=GROUP_ID_B64)
    )
    group_body = mock.send_log[-1]
    assert (group_body.get("params") or {}).get("groupId") == GROUP_ID_B64
    assert "recipient" not in (group_body.get("params") or {}), "group dispatch must NOT include recipient"

    # DM reply: no thread_id, must use recipient
    await adapter.send(ChannelReply(channel="signal", channel_user_id=OWNER_ID, text="dm reply"))
    dm_body = mock.send_log[-1]
    assert (dm_body.get("params") or {}).get("recipient") == OWNER_ID
    assert "groupId" not in (dm_body.get("params") or {})
