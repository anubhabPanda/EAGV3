"""WebUI adapter tests.

Wire-format basis: course-defined WebSocket frame protocol documented
in docs/ADAPTER_GUIDE.md §WebUI.

Six structural tests + one behavioural test (typing indicator pre-frame).
"""

from __future__ import annotations

from datetime import datetime

import pytest

from glc.channels.catalogue.webui.adapter import Adapter
from glc.channels.envelope import ChannelMessage, ChannelReply
from glc.security.pairing import get_pairing_store
from tests.channels.mocks.webui_mock import OWNER_ID, STRANGER_ID, WebuiMock


@pytest.fixture
def mock():
    return WebuiMock()


@pytest.fixture
def pair_owner():
    store = get_pairing_store()
    store.force_pair_owner("webui", OWNER_ID, user_handle="owner")
    yield
    store.revoke("webui", OWNER_ID)


@pytest.mark.asyncio
async def test_on_message_owner_returns_valid_envelope(mock, pair_owner):
    adapter = Adapter(config={"mock": mock})
    ev = mock.queue_owner_message("hello from owner")
    msg = await adapter.on_message(ev)
    assert isinstance(msg, ChannelMessage)
    assert msg.channel == "webui"
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
    """A reply produces an `agent_reply` frame. The behavioural test
    asserts the typing pre-frame; this test asserts the final frame
    shape."""
    adapter = Adapter(config={"mock": mock})
    reply = ChannelReply(channel="webui", channel_user_id=OWNER_ID, text="hi back")
    await adapter.send(reply)
    assert len(mock.send_log) >= 1
    final = mock.send_log[-1]
    assert final.get("type") == "agent_reply"
    assert final.get("text") == "hi back"
    assert final.get("typing") is False, "final frame must mark typing as done"


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
    reply = ChannelReply(channel="webui", channel_user_id=OWNER_ID, text="x")
    result = await adapter.send(reply)
    assert isinstance(result, dict)
    assert result.get("status") == 429 or result.get("code") == 429


@pytest.mark.asyncio
async def test_allowlist_silently_drops_stranger_in_public(mock):
    adapter = Adapter(config={"mock": mock, "is_public_channel": True})
    ev = mock.queue_stranger_message("hi from public")
    msg = await adapter.on_message(ev)
    assert msg is None or msg.trust_level == "untrusted"


@pytest.mark.asyncio
async def test_channel_specific_behaviour_typing_indicator(mock, pair_owner):
    """The WebUI is the only channel where the user is staring at the
    screen waiting for a reply. Without a typing indicator, the
    interface feels broken during the seconds the agent takes to
    produce a response.

    The adapter must emit two frames per ChannelReply:
      1. `{type: "agent_reply", text: "", typing: true}` BEFORE the
         agent's response is ready
      2. `{type: "agent_reply", text: "<reply>", typing: false}` when
         the response lands

    The test inspects send_log for the ordering and content."""
    adapter = Adapter(config={"mock": mock})
    reply = ChannelReply(channel="webui", channel_user_id=OWNER_ID, text="here you go")
    await adapter.send(reply)
    assert len(mock.send_log) >= 2, "WebUI replies must emit typing pre-frame + final frame"
    typing_frame = mock.send_log[-2]
    final_frame = mock.send_log[-1]
    assert typing_frame.get("typing") is True, "first frame must mark typing=true"
    assert typing_frame.get("text", "") == "", "typing pre-frame must carry empty text"
    assert final_frame.get("typing") is False, "second frame must mark typing=false"
    assert final_frame.get("text") == "here you go"
