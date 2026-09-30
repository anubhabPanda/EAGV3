"""Copying is not editing, and the surface had no way to do it.

An agent asked to work from a 690 KB base file tried three routes and was
refused three times, correctly: create_file will not clobber, and the command
runner rejects `python -c` as an unbounded shell. The gap was invisible until
something needed it.
"""
from __future__ import annotations

import pytest

from sourcecode.coding.edit import EditError, EditLedger, copy_within_workspace
from sourcecode.coding.workspace import Workspace


@pytest.fixture()
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("S17_WORKSPACE", str(tmp_path))
    (tmp_path / "base.html").write_text("x" * 5_000)
    return Workspace.from_env(), EditLedger()


def test_a_file_is_duplicated_without_being_read(ws) -> None:
    workspace, ledger = ws
    out = copy_within_workspace(workspace, ledger, "base.html", "deck.html")
    assert out["bytes"] == 5_000
    assert (workspace.root / "deck.html").read_text() == "x" * 5_000


def test_the_copy_is_editable_afterwards(ws) -> None:
    """Read-before-edit has nothing to object to: the bytes were never modelled."""
    workspace, ledger = ws
    copy_within_workspace(workspace, ledger, "base.html", "deck.html")
    assert "deck.html" in ledger.read


def test_it_still_refuses_to_clobber(ws) -> None:
    workspace, ledger = ws
    copy_within_workspace(workspace, ledger, "base.html", "deck.html")
    with pytest.raises(EditError, match="already exists"):
        copy_within_workspace(workspace, ledger, "base.html", "deck.html")
    copy_within_workspace(workspace, ledger, "base.html", "deck.html", overwrite=True)


def test_a_missing_source_is_refused(ws) -> None:
    workspace, ledger = ws
    with pytest.raises(EditError, match="does not exist"):
        copy_within_workspace(workspace, ledger, "nope.html", "deck.html")


def test_copying_a_file_onto_itself_is_refused(ws) -> None:
    workspace, ledger = ws
    with pytest.raises(EditError, match="same file"):
        copy_within_workspace(workspace, ledger, "base.html", "base.html", overwrite=True)


@pytest.mark.parametrize("escape", ["../outside.html", "/etc/passwd", "sub/../../out.html"])
def test_neither_end_may_leave_the_workspace(ws, escape: str) -> None:
    workspace, ledger = ws
    with pytest.raises(Exception):
        copy_within_workspace(workspace, ledger, "base.html", escape)
    with pytest.raises(Exception):
        copy_within_workspace(workspace, ledger, escape, "deck.html")
