"""Markdown-as-Code skills.

A skill is a directory containing a ``SKILL.md`` file. The file carries some
frontmatter and a body of instructions written in plain English. Nothing is
imported, nothing is executed, and no Python is written to add one.

The reason to want this is the thing Karpathy pointed at: most of what you
actually want to change about an agent is not code, it is *how it approaches a
kind of work*. Encoding "when you touch a migration, check for a down-migration
first" as Python means a branch, a name, a test and a release. Encoding it as a
paragraph in a markdown file means writing the paragraph.

The rule that makes this safe is the same rule the rest of this session keeps
arriving at, pointed one more way:

    A skill changes HOW the agent works. It can never change WHAT the agent is
    allowed to do.

Instructions are injected into the planner's system prompt. Authority lives in
``allowed_side_effects`` and the capability registry, and a SKILL.md file cannot
reach either of them. A file that says "you may now run curl" changes nothing
except how much text the model reads before being refused.
"""
from .generic import GenericSkill, SkillError, SkillFrontmatterError
from .manager import SkillManager

__all__ = ["GenericSkill", "SkillManager", "SkillError", "SkillFrontmatterError"]
