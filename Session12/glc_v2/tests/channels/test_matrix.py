"""Matrix adapter tests.

Wire-format basis: Matrix client-server API.
https://spec.matrix.org/v1.10/client-server-api/

Six structural tests + one behavioural test (mxc:// media download).
"""

from __future__ import annotations

from datetime import datetime

import pytest

from glc.channels.catalogue.matrix.adapter import Adapter
from glc.channels.envelope import ChannelMessage, ChannelReply
from glc.security.pairing import get_pairing_store
from tests.channels.mocks.matrix_mock import OWNER_ID, STRANGER_ID, MatrixMock


@pytest.fixture
def mock():
    return MatrixMock()


@pytest.fixture
def pair_owner():
    store = get_pairing_store()
    store.force_pair_owner("matrix", OWNER_ID, user_handle="owner")
    yield
    store.revoke("matrix", OWNER_ID)


@pytest.mark.asyncio
async def test_on_message_owner_returns_valid_envelope(mock, pair_owner):
    adapter = Adapter(config={"mock": mock})
    ev = mock.queue_owner_message("hello from owner")
    msg = await adapter.on_message(ev)
    assert isinstance(msg, ChannelMessage)
    assert msg.channel == "matrix"
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
    """Outbound shape: `{"msgtype": "m.text", "body": "..."}`. Adapters
    that put text under `text` (the Slack-style field) fail."""
    adapter = Adapter(config={"mock": mock})
    reply = ChannelReply(channel="matrix", channel_user_id=OWNER_ID, text="hi back")
    await adapter.send(reply)
    assert len(mock.send_log) == 1
    body = mock.send_log[0]
    assert body.get("msgtype") == "m.text"
    assert body.get("body") == "hi back"


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
    reply = ChannelReply(channel="matrix", channel_user_id=OWNER_ID, text="x")
    result = await adapter.send(reply)
    assert isinstance(result, dict)
    assert result.get("status") == 429 or result.get("errcode") == "M_LIMIT_EXCEEDED"


@pytest.mark.asyncio
async def test_allowlist_silently_drops_stranger_in_public(mock):
    adapter = Adapter(config={"mock": mock, "is_public_channel": True})
    ev = mock.queue_stranger_message("hi from public")
    msg = await adapter.on_message(ev)
    assert msg is None or msg.trust_level == "untrusted"


@pytest.mark.asyncio
async def test_channel_specific_behaviour_mxc_media_download(mock, pair_owner):
    """`m.image` events carry an `mxc://` URL in `content.url`. The
    adapter must resolve the URL through `mock.download_media(url)`
    (the real client hits `/_matrix/media/v3/download/{serverName}/{mediaId}`)
    and surface the bytes as an Attachment of kind `image`.

    Adapters that surface the raw mxc:// string as the ref ship a
    broken artifact handle the agent runtime cannot dereference."""
    adapter = Adapter(config={"mock": mock})
    ev = mock.queue_image_message(mxc_url="mxc://matrix.org/abc123")
    msg = await adapter.on_message(ev)
    assert msg is not None
    assert len(msg.attachments) >= 1
    img = next((a for a in msg.attachments if a.kind == "image"), None)
    assert img is not None, "m.image event must produce an Attachment of kind='image'"
    assert img.ref != "mxc://matrix.org/abc123", (
        "ref must be the dereferenced bytes handle, not the raw mxc URI"
    )
