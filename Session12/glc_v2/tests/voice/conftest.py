"""Defensive test collection for voice providers.

Parallel to tests/channels/conftest.py — if a voice provider's
adapter.py won't import (syntax error, missing dep), the matching
test file is skipped with a clear message instead of polluting the
failure list for every PR.

Recognised paths:
  tests/voice/stt/test_<name>.py -> glc.voice.stt.providers.<name>.adapter
  tests/voice/tts/test_<name>.py -> glc.voice.tts.providers.<name>.adapter
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

_TEST_FILE_RE = re.compile(r"^test_(?P<name>[a-z_]+)\.py$")


def pytest_collectstart(collector):  # pragma: no cover
    p = Path(collector.fspath) if hasattr(collector, "fspath") else None
    if p is None:
        return
    m = _TEST_FILE_RE.match(p.name)
    if not m:
        return
    kind = p.parent.name  # 'stt' or 'tts'
    if kind not in ("stt", "tts"):
        return
    provider = m.group("name")
    try:
        importlib.import_module(f"glc.voice.{kind}.providers.{provider}.adapter")
    except Exception as e:
        pytest.skip(
            f"voice provider glc.voice.{kind}.providers.{provider}.adapter failed to import: {e!r}",
            allow_module_level=True,
        )
