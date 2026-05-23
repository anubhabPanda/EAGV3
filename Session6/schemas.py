
from pydantic import BaseModel
from typing import Literal
from datetime import datetime

class MemoryItem(BaseModel):
    id: str
    kind: Literal["fact", "preference", "tool_outcome", "scratchpad"]
    keywords: list[str]
    descriptor: str            # one short human-readable line
    value: dict                # structured payload
    artifact_id: str | None    # handle into the artifact store (format: "art:<int>")
    source: str
    run_id: str
    goal_id: str | None
    confidence: float
    created_at: datetime


class Artifact(BaseModel):
    id: str                    # artifact ID in format "art:<int>"
    content_type: str
    size_bytes: int
    source: str
    descriptor: str


class Goal(BaseModel):
    id: str
    text: str                  # short imperative description
    done: bool
    attach_artifact_id: str | None  # artifact ID in format "art:<int>"

class Observation(BaseModel):
    goals: list[Goal]
    next_unfinished: Goal | None
    final_answer: str | None  # Populated when all goals are done


class ToolCall(BaseModel):
    name: str
    arguments: dict


class DecisionOutput(BaseModel):
    answer: str | None         # exactly one of these two is populated
    tool_call: ToolCall | None