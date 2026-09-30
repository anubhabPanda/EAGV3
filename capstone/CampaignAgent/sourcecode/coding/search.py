"""Finding things without reading everything.

A repository does not fit in a context window and never will, so the skill is
reading less. Two different questions, two different tools:

* `glob_files` answers "which files exist" by path. Cheap, and it scopes.
* `grep_code` answers "where does this text appear" by content, with the file and
  line, so the next step is a ranged read rather than a whole file.

Both cap their results. An agent that receives four hundred matches has learned
nothing and spent its context finding out.
"""
from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path

from .workspace import Workspace

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
             ".ruff_cache", "dist", "build", ".mypy_cache", ".tox"}
MAX_FILE_BYTES = 2_000_000


def _walk(workspace: Workspace):
    for dirpath, dirnames, filenames in os.walk(workspace.root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            path = Path(dirpath) / name
            yield path, str(path.relative_to(workspace.root))


def glob_files(workspace: Workspace, pattern: str, *, limit: int = 200) -> dict:
    """Files whose path matches a glob, newest first."""
    hits = []
    for path, relative in _walk(workspace):
        rel = relative.replace(os.sep, "/")
        if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(rel.rsplit("/", 1)[-1], pattern):
            hits.append((path.stat().st_mtime, rel))
    hits.sort(reverse=True)
    files = [rel for _mtime, rel in hits[:limit]]
    return {"pattern": pattern, "files": files, "count": len(files),
            "truncated": len(hits) > limit}


def grep_code(workspace: Workspace, pattern: str, *, path_glob: str = "*",
              limit: int = 60, ignore_case: bool = False) -> dict:
    """Lines matching a regex, with file and line number so a ranged read can follow."""
    try:
        matcher = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
    except re.error as error:
        raise ValueError(f"invalid search pattern: {error}") from error

    matches: list[dict] = []
    scanned = 0
    for path, relative in _walk(workspace):
        rel = relative.replace(os.sep, "/")
        if path_glob != "*" and not (fnmatch.fnmatch(rel, path_glob)
                                     or fnmatch.fnmatch(rel.rsplit("/", 1)[-1], path_glob)):
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError):
            continue          # binary or unreadable: not code we can help with
        scanned += 1
        for number, line in enumerate(text.splitlines(), 1):
            if matcher.search(line):
                matches.append({"path": rel, "line": number, "text": line.strip()[:240]})
                if len(matches) >= limit:
                    return {"pattern": pattern, "matches": matches, "files_scanned": scanned,
                            "truncated": True,
                            "hint": "narrow the pattern or the path_glob: this is capped"}
    return {"pattern": pattern, "matches": matches, "files_scanned": scanned,
            "truncated": False}
