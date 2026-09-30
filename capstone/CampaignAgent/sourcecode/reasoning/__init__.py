"""System 2: draft, verify, refine.

Section 1 of this session rests on code having a free judge. Tests are
deterministic, instant, and written by somebody else, which is why a coding
agent can iterate on its own when nothing else can.

Most work is not like that.

"Is this explanation any good?" has no exit code. "Is this the right schema?"
has no exit code. For those, the only judge available is another model call, and
Session 15 measured what that costs: the judge was seven times the price of the
work it graded.

So this module is the expensive path, and it exists to be used exactly where the
cheap one is unavailable:

    If a test can answer the question, run the test.
    If nothing can answer the question, draft, verify, and refine.
    Never do both for the same artifact.

Running System 2 over code that already has a passing suite is paying a model to
have opinions about something you can already prove.
"""
from .verifier import Verdict, Verifier
from .engine import ReasoningEngine, Reasoned
from .jitrl import OptimizedQuery, QueryOptimizer

__all__ = [
    "Verifier", "Verdict", "ReasoningEngine", "Reasoned",
    "QueryOptimizer", "OptimizedQuery",
]
