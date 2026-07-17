"""Pydantic types for the policy engine.

A rule matches on a combination of `tool`, `channel`, `trust_level`, and
arbitrary `condition` fields. Actions are `allow`, `deny`, or
`require_approval`. A `reason` field gives operators human-readable
explanations of verdicts.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Action = Literal["allow", "deny", "require_approval"]
TrustLevel = Literal["owner_paired", "user_paired", "untrusted"]


class PolicyRule(BaseModel):
    """One rule in policy.yaml.

    `tool` accepts a literal tool name or `"*"`. `channel` and `trust_level`
    similarly accept literals or "*". `condition` is a dict of arbitrary
    keys; the engine supports glob (`path_glob`), regex (`*_regex`),
    list membership (`*_in`), and substring matching by default.
    """

    tool: str = "*"
    channel: str = "*"
    trust_level: str = "*"
    condition: dict[str, Any] = Field(default_factory=dict)
    action: Action
    reason: str = ""

    model_config = ConfigDict(extra="forbid")


class PolicyVerdict(BaseModel):
    action: Action
    reason: str
    matched_rule_index: int | None = None

    model_config = ConfigDict(extra="forbid")


class PolicyConfig(BaseModel):
    rules: list[PolicyRule] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
