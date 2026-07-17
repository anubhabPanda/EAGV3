"""ChannelMessage / ChannelReply schema tests."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glc.channels.envelope import Attachment, ChannelMessage, ChannelReply


def test_channel_message_minimum_valid():
    msg = ChannelMessage(
        channel="telegram",
        channel_user_id="42",
        user_handle="me",
        text="hi",
        trust_level="owner_paired",
        arrived_at=datetime.now(UTC),
    )
    assert msg.trust_level == "owner_paired"
    assert msg.attachments == []


def test_channel_message_requires_trust_level():
    with pytest.raises(ValidationError):
        ChannelMessage(
            channel="telegram",
            channel_user_id="42",
            user_handle="me",
            arrived_at=datetime.now(UTC),
        )


def test_channel_message_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        ChannelMessage(
            channel="telegram",
            channel_user_id="42",
            user_handle="me",
            trust_level="owner_paired",
            arrived_at=datetime.now(UTC),
            unexpected="field",
        )


def test_trust_level_literal_enforced():
    with pytest.raises(ValidationError):
        ChannelMessage(
            channel="x",
            channel_user_id="1",
            user_handle="x",
            trust_level="god_mode",
            arrived_at=datetime.now(UTC),
        )


def test_attachment_kind_enforced():
    ok = Attachment(kind="image", ref="art:abc123", mime="image/png")
    assert ok.kind == "image"
    with pytest.raises(ValidationError):
        Attachment(kind="hologram", ref="art:abc")


def test_channel_reply_round_trip():
    r = ChannelReply(channel="discord", channel_user_id="42", text="ok")
    blob = r.model_dump_json()
    back = ChannelReply.model_validate_json(blob)
    assert back == r
