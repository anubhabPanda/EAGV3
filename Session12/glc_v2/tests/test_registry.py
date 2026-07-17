"""Channel registry discovery."""

from __future__ import annotations

from glc.channels.base import ChannelAdapter
from glc.channels.registry import discover, get, instantiate, list_channels


def test_discover_returns_fifteen_channels():
    d = discover()
    assert len(d) == 15
    for name, cls in d.items():
        assert isinstance(name, str)
        assert issubclass(cls, ChannelAdapter)
        assert cls.name == name


def test_list_channels_is_sorted():
    names = list_channels()
    assert names == sorted(names)
    assert "telegram" in names
    assert "local_mic" in names


def test_get_returns_class_or_none():
    assert get("telegram") is not None
    assert get("not_a_real_channel") is None


def test_instantiate_returns_adapter():
    inst = instantiate("telegram", config={"foo": "bar"})
    assert isinstance(inst, ChannelAdapter)
    assert inst.config == {"foo": "bar"}


def test_instantiate_unknown_raises():
    import pytest

    with pytest.raises(KeyError):
        instantiate("definitely_unknown", config={})
