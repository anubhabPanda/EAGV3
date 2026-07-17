"""Per-channel allowlists.

Default posture: empty `allowed_senders` means owner-only for DM channels
and mention-only for public channels (when `mention_only_in_public: true`).
The owner is whichever `channel_user_id` is currently in the pairings
table with trust_level == owner_paired.
"""

from __future__ import annotations

from glc.config import load_channels


def _entry(channel: str) -> dict:
    cfg = load_channels()
    defaults = cfg.get("defaults") or {}
    ch_cfg = (cfg.get("channels") or {}).get(channel) or {}
    out = {
        "allowed_senders": ch_cfg.get("allowed_senders", defaults.get("allowed_senders", [])),
        "mention_only_in_public": ch_cfg.get(
            "mention_only_in_public",
            defaults.get("mention_only_in_public", True),
        ),
        "enabled": ch_cfg.get("enabled", True),
    }
    return out


def allowed(
    channel: str,
    channel_user_id: str,
    *,
    owner_ids: list[str] | None = None,
    is_public_channel: bool = False,
    was_mentioned: bool = False,
) -> tuple[bool, str]:
    """Returns (ok, reason). If the channel itself is disabled, returns False.
    If `owner_ids` is provided, owners always pass. Otherwise, the call is
    allowed if `channel_user_id` is in `allowed_senders`. In public channels
    with mention_only_in_public, an explicit mention is also required."""
    cfg = _entry(channel)
    if not cfg["enabled"]:
        return False, f"channel '{channel}' is disabled in channels.yaml"
    owners = owner_ids or []
    if channel_user_id in owners:
        if is_public_channel and cfg["mention_only_in_public"] and not was_mentioned:
            return False, "owner in public channel must be explicitly mentioned"
        return True, ""
    allowed_list = cfg["allowed_senders"] or []
    if channel_user_id not in allowed_list:
        return False, f"sender {channel_user_id!r} not in allowed_senders for '{channel}'"
    if is_public_channel and cfg["mention_only_in_public"] and not was_mentioned:
        return False, "sender in public channel must be explicitly mentioned"
    return True, ""
