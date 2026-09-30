"""Editing by anchor, with two preconditions the agent cannot talk its way past.

**Read before you edit.** A run may only edit a file it has already read. This is
enforced here, not requested in a prompt. An edit written from memory is how an
agent silently reverts work it never saw, and the model has no way to know it has
done it.

**The anchor must be unique.** An edit names the exact text to replace. If that
text appears twice the edit is refused, because the agent has not said which one
it means. Making the anchor unique forces it to include enough surrounding code
to prove it knows where it is, which is a comprehension check disguised as an
argument requirement.

Anchors rather than unified diffs, deliberately. A diff needs correct line
numbers and context lines; models are poor at both, so a diff-based agent burns
its iterations on the patch format instead of the bug. An anchor needs no
arithmetic at all.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .guard import guard_path
from .workspace import Workspace


class EditError(ValueError):
    """The edit was not well-formed, so it never reached the file."""


@dataclass
class EditLedger:
    """What this run has read, and therefore what it is allowed to change."""

    read: set[str] = field(default_factory=set)

    def record_read(self, relative: str) -> None:
        self.read.add(str(relative))

    def require_read(self, relative: str) -> None:
        if str(relative) not in self.read:
            raise EditError(
                f"cannot edit {relative} before reading it. "
                "Read the file first: editing from memory rewrites code you never saw."
            )


def read_code(workspace: Workspace, ledger: EditLedger, relative: str, *,
              offset: int = 1, limit: int | None = None) -> dict:
    """Read part of a file. Ranged by default, because context is the budget."""
    path = workspace.resolve(relative)
    if not path.is_file():
        raise EditError(f"not a file: {relative}")
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(1, offset)
    end = len(lines) if limit is None else min(len(lines), start + limit - 1)
    window = lines[start - 1:end]
    # Reading any part of a file counts: the agent has now seen this file's real
    # contents rather than its recollection of them.
    ledger.record_read(relative)
    return {
        "path": relative,
        "start_line": start,
        "end_line": end,
        "total_lines": len(lines),
        "truncated": end < len(lines),
        "text": "\n".join(f"{start + i:>6}  {line}" for i, line in enumerate(window)),
    }


def apply_edit(workspace: Workspace, ledger: EditLedger, relative: str, *,
               old_string: str, new_string: str, replace_all: bool = False) -> dict:
    """Replace an exact, unique string. Refuses on anything ambiguous."""
    guard_path(relative, action="edit")
    ledger.require_read(relative)

    path = workspace.resolve(relative)
    if not path.is_file():
        raise EditError(f"not a file: {relative}")
    if old_string == new_string:
        raise EditError("old_string and new_string are identical; nothing to do")
    if not old_string:
        raise EditError("old_string must not be empty; use create_file for a new file")

    original = path.read_text(encoding="utf-8")
    occurrences = original.count(old_string)

    if occurrences == 0:
        raise EditError(
            f"old_string does not appear in {relative}. It must match exactly, "
            "including indentation and whitespace."
        )
    if occurrences > 1 and not replace_all:
        raise EditError(
            f"old_string appears {occurrences} times in {relative}. Include more "
            "surrounding context so it names one place, or pass replace_all when "
            "you really mean every one."
        )

    updated = (original.replace(old_string, new_string) if replace_all
               else original.replace(old_string, new_string, 1))
    path.write_text(updated, encoding="utf-8")
    return {
        "path": relative,
        "replaced": occurrences if replace_all else 1,
        "occurrences_found": occurrences,
        "bytes_before": len(original),
        "bytes_after": len(updated),
    }


def create_file(workspace: Workspace, ledger: EditLedger, relative: str, *,
                content: str, overwrite: bool = False) -> dict:
    """Write a whole file. Only for files that do not exist yet, unless forced."""
    guard_path(relative, action="create")
    path = workspace.resolve(relative)
    if path.exists() and not overwrite:
        raise EditError(
            f"{relative} already exists. Edit it by anchor, or pass overwrite to "
            "replace the whole file, which throws away anything you did not read."
        )
    if path.exists() and overwrite:
        ledger.require_read(relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    ledger.record_read(relative)
    return {"path": relative, "bytes": len(content), "created": True}


def copy_within_workspace(workspace, ledger, source: str, destination: str,
                          *, overwrite: bool = False) -> dict:
    """Duplicate a file inside the workspace without reading it into context.

    This exists because the coding surface had no way to do it, and the gap was
    invisible until an agent needed it. It had `create_file`, which cannot
    reproduce 690 KB it has not read, and `run_command`, which correctly refuses
    `python -c` as an unbounded shell. Four capabilities, each individually
    right, and no path between them: the agent tried three approaches, was
    refused three times, and every refusal was correct.

    Copying is not editing. It reads no content into the model, so it is exempt
    from read-before-edit: there is nothing to have read. It stays inside the
    workspace and it still refuses to clobber, because silently replacing a file
    is the thing read-before-edit exists to prevent.
    """
    src = workspace.resolve(source)
    dst = workspace.resolve(destination)
    if not src.is_file():
        raise EditError(f"cannot copy {source}: it does not exist")
    if dst.exists() and not overwrite:
        raise EditError(
            f"{destination} already exists. Pass overwrite when you mean to replace it."
        )
    if src == dst:
        raise EditError("source and destination are the same file")

    import shutil

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    size = dst.stat().st_size
    # The copy is now readable-for-edit: the bytes came from a file the
    # workspace already trusted, not from anything the model wrote.
    ledger.read.add(str(destination))
    return {"copied": True, "source": source, "destination": destination, "bytes": size}
