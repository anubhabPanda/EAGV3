"""Per-channel per-user rate limits."""

from __future__ import annotations

import time

from glc.security.rate_limits import RateLimiter


def test_under_cap_passes():
    r = RateLimiter(default_mpm=3, default_tpm=2)
    for _ in range(3):
        ok, _ = r.check_message("telegram", "42")
        assert ok


def test_over_cap_returns_429():
    r = RateLimiter(default_mpm=2, default_tpm=2)
    r.check_message("telegram", "42")
    r.check_message("telegram", "42")
    ok, why = r.check_message("telegram", "42")
    assert ok is False
    assert "limit" in why.lower()


def test_per_user_isolation():
    r = RateLimiter(default_mpm=1, default_tpm=1)
    assert r.check_message("telegram", "42")[0]
    assert r.check_message("telegram", "43")[0]


def test_per_channel_isolation():
    r = RateLimiter(default_mpm=1, default_tpm=1)
    assert r.check_message("telegram", "42")[0]
    assert r.check_message("discord", "42")[0]


def test_window_slides(monkeypatch):
    r = RateLimiter(default_mpm=1, default_tpm=1)
    r.check_message("telegram", "42")
    assert r.check_message("telegram", "42")[0] is False
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 61)
    assert r.check_message("telegram", "42")[0] is True


def test_yaml_configuration_per_channel():
    r = RateLimiter(default_mpm=10, default_tpm=10)
    r.configure_from_yaml(
        {
            "defaults": {"rate_limits": {"messages_per_minute": 10, "tool_calls_per_minute": 10}},
            "channels": {"telegram": {"rate_limits": {"messages_per_minute": 1}}},
        }
    )
    assert r.check_message("telegram", "1")[0]
    assert r.check_message("telegram", "1")[0] is False
    # Other channels still have default cap.
    for _ in range(5):
        assert r.check_message("discord", "1")[0]


def test_tool_calls_separate_from_messages():
    r = RateLimiter(default_mpm=1, default_tpm=1)
    assert r.check_message("x", "1")[0]
    # Tool call quota is its own bucket.
    assert r.check_tool_call("x", "1")[0]
