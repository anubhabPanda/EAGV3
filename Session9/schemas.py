"""Typed contracts every layer in the S7 agent talks in.

One small file, read top-to-bottom. Every other module imports from here, so
the boundary between layers is a Pydantic model rather than a free-form dict.

Session 7 adds one optional field on `MemoryItem`: `embedding`. Items of
kind `fact`, `preference`, and `tool_outcome` carry a vector embedding
written by Memory at insert time. The embedding underlies FAISS vector
search. Items of kind `scratchpad` are run-scoped and skip embedding.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def new_id(prefix: str = "id") -> str:
    return f"{prefix}:{uuid4().hex[:8]}"


# ── Memory ──────────────────────────────────────────────────────────────────

MemoryKind = Literal["fact", "preference", "tool_outcome", "scratchpad"]


class MemoryItem(BaseModel):
    """One record in memory. Reads happen by vector similarity first
    (FAISS over the `embedding` field) with keyword overlap as the
    fallback when vector search returns nothing. Bytes never live here;
    they live in the artifact store."""

    id: str
    kind: MemoryKind
    keywords: list[str] = Field(default_factory=list)
    descriptor: str                              # one short human-readable line
    value: dict = Field(default_factory=dict)    # structured payload
    artifact_id: str | None = None
    embedding: list[float] | None = None         # set by Memory at write time
    source: str
    run_id: str
    goal_id: str | None = None
    confidence: float = 1.0
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── Artifacts ───────────────────────────────────────────────────────────────

class Artifact(BaseModel):
    id: str
    content_type: str
    size_bytes: int
    source: str
    descriptor: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── Goals & Observations ────────────────────────────────────────────────────

class Goal(BaseModel):
    id: str
    text: str
    done: bool = False
    attach_artifact_id: str | None = None        # Perception sets this when the goal needs raw bytes


class Observation(BaseModel):
    goals: list[Goal]

    @property
    def all_done(self) -> bool:
        return bool(self.goals) and all(g.done for g in self.goals)

    def next_unfinished(self) -> Goal | None:
        return next((g for g in self.goals if not g.done), None)


# ── Decision output ─────────────────────────────────────────────────────────

class ToolCall(BaseModel):
    name: str
    arguments: dict


class DecisionOutput(BaseModel):
    """Decision emits exactly one of these two. `answer` carries arbitrary
    semantic work (summarise, extract, compare, translate) inside its text."""

    answer: str | None = None
    tool_call: ToolCall | None = None

    @property
    def is_answer(self) -> bool:
        return self.answer is not None


# ── Session 8: multi-agent growing graph ────────────────────────────────────

class NodeSpec(BaseModel):
    """One node the orchestrator will eventually run. `inputs` items are
    either ArtifactRef ids (`art:...`), upstream node ids (`n:...`), or
    free-form strings the receiving skill knows how to use."""

    skill: str
    inputs: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


# Session 9: structured failure taxonomy for the Browser skill. Other skills
# leave error_code=None and fall through to recovery.classify_failure's text
# heuristics. This field is additive and breaks no existing carriers.
ErrorCode = Literal[
    "gateway_blocked",       # CAPTCHA, login wall, geo-block, page never rendered
    "extraction_failed",     # rendered but no useful content
    "interaction_failed",    # could not complete the goal within turn cap
    "timeout",               # wall-clock cap hit
    "vlm_unavailable",       # all vision providers refused or 503'd
]


class AgentResult(BaseModel):
    """What every skill returns. The boundary between flow.py and a skill
    is exactly this model — orchestrator and skills never share dicts."""

    success: bool
    agent_name: str
    output: dict = Field(default_factory=dict)
    artifacts: list[str] = Field(default_factory=list)
    successors: list[NodeSpec] = Field(default_factory=list)
    cost: float = 0.0
    elapsed_s: float = 0.0
    provider: str = ""
    error: str | None = None
    # Session 9: structured failure code for the Browser skill (other skills
    # leave it None and fall through to recovery's text heuristics).
    error_code: ErrorCode | None = None


class BrowserOutput(BaseModel):
    """Session 9: typed payload the Browser skill writes into AgentResult.output.

    `path` is the cascade layer the skill actually used.  Downstream skills
    consume `content` through the normal output pipe; only replay and the
    Planner's failure routing care about `path`.
    """

    url: str
    goal: str
    path: Literal["extract", "deterministic", "a11y", "vision"]
    turns: int = 0
    content: str | None = None
    actions: list[dict] = Field(default_factory=list)
    final_url: str | None = None


class NodeState(BaseModel):
    """Per-node persistent record. `prompt_sent` is the load-bearing field
    for replay — replay shows the student the exact bytes that hit the
    gateway, not a reconstruction."""

    node_id: str
    skill: str
    status: Literal["pending", "running", "complete", "failed", "skipped"]
    inputs: list[str] = Field(default_factory=list)
    result: AgentResult | None = None
    prompt_sent: str | None = None
    started_at: float | None = None
    completed_at: float | None = None
    retries: int = 0
