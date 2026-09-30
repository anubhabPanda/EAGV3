"""Capability workers, as module-level functions.

These used to be forty-eight closures defined inside ``AgentRuntime.run``, which
is why that function was 1,008 lines. They were closures for one reason: to
capture seven values from the enclosing scope. A dataclass carries seven values
perfectly well, and a worker at module level can be read, tested and grepped on
its own.
"""
from .context import RunContext

__all__ = ["RunContext"]
