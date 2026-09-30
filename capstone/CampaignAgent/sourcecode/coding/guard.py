"""What the agent may not touch.

Session 15 needed a model to judge whether work was done, and that judge cost
seven times the work it graded. Code is the first place this course gets a judge
for free: the tests are deterministic, they already exist, and somebody else
wrote them.

That only holds while the agent cannot edit them.

Given a failing test and an instruction to make the suite green, a model will
find the cheap route unless something stops it. Delete the test. Skip it. Weaken
the assertion. Catch the exception it was checking for. Each one turns the suite
green and leaves the bug exactly where it was.

So test paths are refused here, in code, before an edit is attempted. Not asked
for politely in a system prompt.
"""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path

# Anything matching these is the judge, not the work.
DEFAULT_PROTECTED = (
    "tests/**", "test/**", "**/tests/**", "**/test_*.py", "**/*_test.py",
    "conftest.py", "**/conftest.py",
    "pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml", ".github/**",
)


class GuardError(PermissionError):
    """The agent tried to change something it is not allowed to change."""


def protected_patterns() -> tuple[str, ...]:
    configured = os.getenv("S17_PROTECTED_PATHS", "").strip()
    if configured:
        return tuple(p.strip() for p in configured.split(",") if p.strip())
    return DEFAULT_PROTECTED


def is_protected(relative: str, patterns: tuple[str, ...] | None = None) -> str | None:
    """Return the pattern that protects this path, or None."""
    # NB: not lstrip("./") — that strips any leading "." or "/" characters, so
    # ".github/workflows" would become "github/workflows" and every dotted path
    # would quietly escape the guard.
    rel = str(relative).replace(os.sep, "/")
    while rel.startswith("./"):
        rel = rel[2:]
    rel = rel.lstrip("/")
    for pattern in patterns or protected_patterns():
        # fnmatch does not treat "/" specially, so "**/x" needs a plain tail check too.
        if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch("/" + rel, "/" + pattern):
            return pattern
        if pattern.startswith("**/") and fnmatch.fnmatch(rel.rsplit("/", 1)[-1], pattern[3:]):
            return pattern
        if pattern.endswith("/**") and (rel == pattern[:-3] or rel.startswith(pattern[:-3] + "/")):
            return pattern
    return None


def guard_path(relative: str | Path, *, action: str = "edit") -> None:
    """Raise if this path is the judge rather than the work."""
    pattern = is_protected(str(relative))
    if pattern:
        raise GuardError(
            f"refusing to {action} {relative}: it matches protected pattern {pattern!r}. "
            "The tests grade the work; an agent that can edit them grades itself."
        )
