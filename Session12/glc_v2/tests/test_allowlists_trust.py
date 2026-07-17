"""Allowlist enforcement and trust-level classification."""

from __future__ import annotations

from glc.security.allowlists import allowed
from glc.security.pairing import get_pairing_store
from glc.security.trust_level import classify

# Default channels.yaml ships every channel except webui as
# `enabled: false` — this is a security default for fresh installs.
# These tests exercise allowlist policy on an enabled channel.


def test_owner_in_dm_is_allowed():
    ok, _ = allowed("webui", "owner-1", owner_ids=["owner-1"], is_public_channel=False, was_mentioned=False)
    assert ok


def test_unknown_sender_in_dm_is_denied_by_default():
    ok, why = allowed(
        "webui", "stranger-1", owner_ids=["owner-1"], is_public_channel=False, was_mentioned=False
    )
    assert ok is False
    assert "allowed_senders" in why


def test_owner_in_public_without_mention_is_denied():
    ok, why = allowed("webui", "owner-1", owner_ids=["owner-1"], is_public_channel=True, was_mentioned=False)
    assert ok is False
    assert "mention" in why.lower()


def test_owner_in_public_with_mention_is_allowed():
    ok, _ = allowed("webui", "owner-1", owner_ids=["owner-1"], is_public_channel=True, was_mentioned=True)
    assert ok


def test_disabled_channel_blocks_owner():
    # telegram defaults to enabled=false; even the owner cannot reach it
    # until the operator enables the channel in channels.yaml.
    ok, why = allowed("telegram", "owner-1", owner_ids=["owner-1"])
    assert ok is False
    assert "disabled" in why


def test_disabled_channel_blocked(monkeypatch):
    import glc.security.allowlists as al

    def fake_load_channels():
        return {"channels": {"telegram": {"enabled": False}}}

    monkeypatch.setattr(al, "load_channels", fake_load_channels)
    ok, why = allowed("telegram", "owner-1", owner_ids=["owner-1"])
    assert ok is False
    assert "disabled" in why


def test_trust_level_unknown_is_untrusted():
    assert classify("telegram", "no-such-user") == "untrusted"


def test_trust_level_owner_paired():
    get_pairing_store().force_pair_owner("matrix", "owner-1", "owner")
    assert classify("matrix", "owner-1") == "owner_paired"


def test_trust_level_user_paired():
    store = get_pairing_store()
    code, _ = store.issue_code("slack", "U1", "user")
    store.confirm_code(code)
    assert classify("slack", "U1") == "user_paired"
