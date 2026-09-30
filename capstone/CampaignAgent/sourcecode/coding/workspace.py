"""One git checkout the agent is allowed to change, and nothing outside it.

A run gets its own workspace. Every path the agent names is resolved inside it,
symlinks included, and anything that lands outside is refused before it is
opened.

The workspace is a git repository on purpose. Git is how a change is accepted or
thrown away, and it is deliberately outside the agent's reach: the agent writes
code, and a human or a passing test suite decides whether that code survives.
Rejection is `git reset`, not an apology.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


class WorkspaceError(PermissionError):
    """A path escaped the workspace, or the workspace is not usable."""


@dataclass(frozen=True)
class Workspace:
    root: Path

    @classmethod
    def open(cls, root: str | Path) -> Workspace:
        resolved = Path(root).expanduser().resolve()
        if not resolved.is_dir():
            raise WorkspaceError(f"workspace is not a directory: {resolved}")
        return cls(resolved)

    @classmethod
    def from_env(cls) -> Workspace:
        configured = os.getenv("S17_WORKSPACE")
        if not configured:
            raise WorkspaceError("coding capabilities require S17_WORKSPACE")
        return cls.open(configured)

    def resolve(self, relative: str) -> Path:
        """Resolve a caller-supplied path, refusing anything outside the workspace."""
        if os.path.isabs(relative):
            raise WorkspaceError(f"paths must be workspace-relative: {relative}")
        candidate = (self.root / relative).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise WorkspaceError(f"path escapes the workspace: {relative}")
        return candidate

    def relative(self, path: Path) -> str:
        return str(path.resolve().relative_to(self.root))

    # ---------------------------------------------------------------- git

    def _git(self, *args: str, check: bool = True) -> str:
        result = subprocess.run(
            ["git", *args], cwd=self.root, capture_output=True, text=True, timeout=60,
        )
        if check and result.returncode != 0:
            raise WorkspaceError(f"git {' '.join(args)} failed: {result.stderr.strip()[:400]}")
        return result.stdout

    def is_git(self) -> bool:
        try:
            self._git("rev-parse", "--git-dir")
            return True
        except (WorkspaceError, FileNotFoundError, subprocess.SubprocessError):
            return False

    def diff(self) -> str:
        """Everything the agent has changed, as a patch a human can read."""
        return self._git("diff") + self._git("diff", "--cached")

    def changed_files(self) -> list[str]:
        out = self._git("status", "--porcelain")
        return sorted({line[3:].strip() for line in out.splitlines() if line.strip()})

    def reset(self) -> None:
        """Throw the attempt away. This is what rejection looks like."""
        self._git("checkout", "--", ".")
        self._git("clean", "-fd")

    def branch(self, name: str) -> str:
        self._git("checkout", "-B", name)
        return name

    def current_branch(self) -> str:
        return self._git("rev-parse", "--abbrev-ref", "HEAD").strip()
