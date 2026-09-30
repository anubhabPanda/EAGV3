"""The seven things a capability worker needs.

Measured, not guessed: an AST pass over the forty-eight closures inside
``AgentRuntime.run`` found they referenced 165 distinct names from the enclosing
scope, but all but seven were local loop variables (``task``, ``result``,
``hit``, ``item``, ``text``, ``key``, ``path``). What actually crossed the
boundary was this.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sourcecode.capabilities import CapabilityRegistry
from sourcecode.coding.edit import EditLedger
from sourcecode.coding.workspace import Workspace


@dataclass(frozen=True)
class RunContext:
    """Everything a worker may reach for, and nothing else.

    Frozen on purpose. A worker that could reassign the run id or swap the
    registry would be able to change what the run is allowed to do from inside
    a capability, which is the boundary the whole session is about.
    """

    run_id: str
    runtime: Any                 # AgentRuntime, typed loosely to avoid a cycle
    llm: Any                     # TextLLM
    scope: Any                   # MemoryScope
    registry: CapabilityRegistry
    ledger: EditLedger
    transport: Any = None
    goal: str = ""          # the run's prompt; the composer titles a surface with it

    def workspace(self) -> Workspace:
        """Resolved per call: S17_WORKSPACE may legitimately differ per run."""
        return Workspace.from_env()
