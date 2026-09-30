"""A task set is DATA. This module reads it; it never contains one.

The whole reason ``p1`` was deferred is that "was the task resolved?" invites an
answer key, and an answer key in Python is a use case welded into the library. So
the tasks live in a file the reviewer owns and can replace wholesale:

    {"id": "t01", "task": "...", "expectation": "...", "difficulty": "trivial"}

``task`` is the only required field. ``expectation`` is a short natural-language
success criterion the rubric scores against — still data, and still not an answer
key the code can pattern-match. ``difficulty`` is a free-form label used only to
group the report; nothing branches on it.

JSON Lines, a JSON array, ``{"tasks": [...]}`` and YAML all load, because the
point is that a reviewer can bring whatever file they already have.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

#: Fields the loader understands. Anything else a record carries is preserved in
#: :attr:`EvalTask.metadata`, so a richer task file loses nothing.
KNOWN_FIELDS = ("id", "task", "expectation", "difficulty")


@dataclass(frozen=True)
class EvalTask:
    """One task, exactly as the data file described it."""

    id: str
    task: str
    expectation: str | None = None
    difficulty: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_expectation(self) -> bool:
        return bool((self.expectation or "").strip())

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task": self.task,
            "expectation": self.expectation,
            "difficulty": self.difficulty,
            "metadata": dict(self.metadata),
        }


def _record_to_task(record: Any, ordinal: int, origin: str) -> EvalTask:
    if not isinstance(record, dict):
        raise ValueError(f"{origin}: record {ordinal} is not a mapping")
    text = str(record.get("task") or "").strip()
    if not text:
        raise ValueError(f"{origin}: record {ordinal} has no non-empty 'task'")
    expectation = record.get("expectation")
    difficulty = record.get("difficulty")
    return EvalTask(
        id=str(record.get("id") or f"task_{ordinal:03d}"),
        task=text,
        expectation=str(expectation).strip() if expectation is not None else None,
        difficulty=str(difficulty).strip() if difficulty is not None else None,
        metadata={key: value for key, value in record.items() if key not in KNOWN_FIELDS},
    )


def _records(path: Path) -> Iterable[Any]:
    """Every record in the file, whatever container the file chose."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                yield json.loads(stripped)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}: not valid JSON Lines: {error}") from error
        return
    loaded = yaml.safe_load(text) if path.suffix.lower() in {".yaml", ".yml"} else json.loads(text)
    if isinstance(loaded, dict):
        loaded = loaded.get("tasks")
    if not isinstance(loaded, list):
        raise ValueError(f"{path}: expected a list of tasks, or a mapping with a 'tasks' list")
    yield from loaded


def load_tasks(path: str | Path) -> tuple[EvalTask, ...]:
    """Load a task set from a file. Raises rather than silently dropping records."""
    resolved = Path(path).expanduser()
    if not resolved.exists():
        raise FileNotFoundError(f"task file not found: {resolved}")
    tasks = tuple(
        _record_to_task(record, ordinal, str(resolved))
        for ordinal, record in enumerate(_records(resolved), start=1)
    )
    if not tasks:
        raise ValueError(f"{resolved}: no tasks found")
    ids = [task.id for task in tasks]
    duplicates = sorted({identifier for identifier in ids if ids.count(identifier) > 1})
    if duplicates:
        raise ValueError(f"{resolved}: duplicate task ids {duplicates}")
    return tasks


def by_difficulty(tasks: Iterable[EvalTask]) -> dict[str, list[str]]:
    """Task ids grouped by their self-declared difficulty label, for the report."""
    grouped: dict[str, list[str]] = {}
    for task in tasks:
        grouped.setdefault(task.difficulty or "unlabelled", []).append(task.id)
    return grouped
