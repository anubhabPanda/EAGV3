"""One skill, read from one ``SKILL.md`` file.

There is deliberately no ``PytestSkill``, no ``MigrationSkill`` and no registry
of skill *classes*. There is one class, and it reads a file. Adding a skill is
writing markdown; it is never writing Python. The moment a second class appears
here, someone has started encoding behaviour in code again and the whole point
has been lost.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["GenericSkill", "SkillError", "SkillFrontmatterError"]

# Frontmatter is a small, boring subset of YAML on purpose: `key: value` and
# `key: [a, b]`. Pulling in a YAML parser to read six keys would mean a skill
# file could exploit a YAML parser, and skill files are the least trusted thing
# in this package.
_FRONTMATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?", re.S)
_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)[ \t]*:[ \t]*(.*)$")

MAX_INSTRUCTION_CHARS = 8_000


class SkillError(RuntimeError):
    """A skill file could not be used."""


class SkillFrontmatterError(SkillError):
    """A skill file was found but its frontmatter is unusable."""


def _scalar(raw: str) -> Any:
    text = raw.strip()
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [p.strip().strip("'\"") for p in inner.split(",") if p.strip()]
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        text = text[1:-1]
    low = text.lower()
    if low in {"true", "yes", "on"}:
        return True
    if low in {"false", "no", "off"}:
        return False
    return text


def parse_frontmatter(source: str) -> tuple[dict[str, Any], str]:
    """Split a SKILL.md into (frontmatter, body)."""
    match = _FRONTMATTER.match(source)
    if not match:
        raise SkillFrontmatterError(
            "SKILL.md must open with a --- frontmatter block naming at least "
            "'name' and 'description'."
        )
    meta: dict[str, Any] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        found = _KEY.match(line.strip())
        if not found:
            raise SkillFrontmatterError(f"cannot read frontmatter line: {line.strip()!r}")
        meta[found.group(1).strip().lower()] = _scalar(found.group(2))
    return meta, source[match.end():]


@dataclass(frozen=True)
class GenericSkill:
    """A named block of instructions, loaded from markdown.

    ``enabled`` is the toggle the SkillManager flips. A disabled skill stays
    discovered and inspectable; it simply contributes no text.
    """

    name: str
    description: str
    instructions: str
    path: Path
    when_to_use: str = ""
    keywords: tuple[str, ...] = ()
    always: bool = False
    enabled: bool = True
    meta: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_file(cls, path: str | Path) -> "GenericSkill":
        p = Path(path)
        try:
            source = p.read_text(encoding="utf-8")
        except OSError as exc:  # unreadable file, wrong permissions, dangling link
            raise SkillError(f"cannot read {p}: {exc}") from exc

        meta, body = parse_frontmatter(source)
        name = str(meta.get("name") or "").strip()
        description = str(meta.get("description") or "").strip()
        if not name:
            raise SkillFrontmatterError(f"{p}: frontmatter needs a 'name'")
        if not description:
            raise SkillFrontmatterError(f"{p}: frontmatter needs a 'description'")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", name):
            raise SkillFrontmatterError(
                f"{p}: name {name!r} must be lowercase letters, digits, '-' or '_'. "
                "It appears in the manifest the model reads, so it has to be stable "
                "and boring."
            )

        instructions = body.strip()
        if not instructions:
            raise SkillError(f"{p}: the body is empty, so the skill would inject nothing")
        if len(instructions) > MAX_INSTRUCTION_CHARS:
            # Section 5 of the lesson, arriving from the other direction: a skill
            # that pastes a whole style guide into every single planning call has
            # not taught the agent anything, it has just spent the context that
            # was supposed to hold the code.
            raise SkillError(
                f"{p}: instructions are {len(instructions)} characters, over the "
                f"{MAX_INSTRUCTION_CHARS} limit. A skill is a page, not a manual: "
                "every planning call pays for this text."
            )

        keywords = meta.get("keywords") or []
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",") if k.strip()]

        return cls(
            name=name,
            description=description,
            instructions=instructions,
            path=p,
            when_to_use=str(meta.get("when_to_use") or "").strip(),
            keywords=tuple(str(k).lower() for k in keywords),
            always=bool(meta.get("always", False)),
            enabled=bool(meta.get("enabled", True)),
            meta=meta,
        )

    # -- matching ---------------------------------------------------------

    def matches(self, goal: str) -> bool:
        """Should this skill be injected for this goal?

        Deliberately dumb: substring matching on declared keywords. A model
        deciding which skills are relevant would be a second planning call
        before every planning call, and would be wrong in ways nobody can debug.
        """
        if self.always:
            return True
        if not self.keywords:
            return False
        haystack = goal.lower()
        return any(k in haystack for k in self.keywords)

    def render(self) -> str:
        """The text injected into the planner's system prompt."""
        header = f"## Skill: {self.name}\n{self.description}"
        if self.when_to_use:
            header += f"\nUse when: {self.when_to_use}"
        return f"{header}\n\n{self.instructions}".strip()
