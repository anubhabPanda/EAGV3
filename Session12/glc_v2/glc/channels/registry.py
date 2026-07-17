"""Discover adapter modules under glc/channels/catalogue/<name>/adapter.py.

An adapter module is registered if it exposes a `class Adapter(ChannelAdapter)`.
Registration is best-effort: a broken adapter logs a warning and is skipped
so one bad student PR cannot break the gateway boot.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any

from glc.channels.base import ChannelAdapter

CATALOGUE_PACKAGE = "glc.channels.catalogue"


def discover() -> dict[str, type[ChannelAdapter]]:
    """Returns {channel_name: Adapter class}. Channels whose adapter is
    still a stub (raises NotImplementedError at class load time)
    register fine; instantiation works, calls fail with a clear message."""
    out: dict[str, type[ChannelAdapter]] = {}
    pkg = importlib.import_module(CATALOGUE_PACKAGE)
    for _, name, ispkg in pkgutil.iter_modules(pkg.__path__):
        if not ispkg:
            continue
        try:
            mod = importlib.import_module(f"{CATALOGUE_PACKAGE}.{name}.adapter")
        except Exception as e:  # pragma: no cover
            print(f"[glc.registry] failed to import {name}: {e!r}")
            continue
        cls = getattr(mod, "Adapter", None)
        if isinstance(cls, type) and issubclass(cls, ChannelAdapter):
            out[name] = cls
    return out


def get(name: str) -> type[ChannelAdapter] | None:
    return discover().get(name)


def list_channels() -> list[str]:
    return sorted(discover().keys())


def instantiate(name: str, config: dict[str, Any] | None = None) -> ChannelAdapter:
    cls = get(name)
    if cls is None:
        raise KeyError(f"unknown channel '{name}'")
    return cls(config=config)
