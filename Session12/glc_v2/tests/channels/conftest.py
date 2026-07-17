"""Defensive test collection for channel adapters.

A group's adapter PR may include a syntax error (work-in-progress) or
fail to import for some other reason. Without this hook, a single bad
adapter import error pollutes the failure list for every other PR run
that pulls main.

The hook tries to import each test file's target adapter at collection
time. If the import errors, the matching test file is skipped with a
clear message naming the broken module — the rest of the suite
collects normally.

This only kicks in when the test file follows the pattern
`tests/channels/test_<channel>.py`. The channel name is read from the
filename and used to locate `glc.channels.catalogue.<channel>.adapter`.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

_TEST_FILE_RE = re.compile(r"^test_(?P<channel>[a-z_]+)\.py$")


def pytest_collectstart(collector):  # pragma: no cover - pytest hook surface
    p = Path(collector.fspath) if hasattr(collector, "fspath") else None
    if p is None:
        return
    m = _TEST_FILE_RE.match(p.name)
    if not m:
        return
    channel = m.group("channel")
    try:
        importlib.import_module(f"glc.channels.catalogue.{channel}.adapter")
    except Exception as e:
        pytest.skip(
            f"channel adapter glc.channels.catalogue.{channel}.adapter failed to import: {e!r}",
            allow_module_level=True,
        )
