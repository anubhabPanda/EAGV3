"""Draft, verify, refine, with a bound on how long that may go on.

The loop is three lines of idea and one line of discipline:

    draft   ->  verify  ->  good enough?  ->  done
                   |             no
                   +-------> refine ------+

The discipline is that it always terminates, and always returns something. Two
rules do that work.

**Fast path.** A verdict at or above the threshold ends the loop immediately. No
extra polish, no second opinion on an answer already judged good. The default is
85 rather than 100 because a loop that demands perfection from a scorer that
cannot deliver it will refine until it runs out of budget, and the last draft is
usually no better than the third.

**Best attempt, not last attempt.** When refinements run out, the engine returns
the highest-scoring draft it saw, which is frequently not the final one.
Refinement is not monotonic: a draft that fixes the critique often breaks
something the critique never mentioned. Returning the last attempt silently
throws away better work that the loop already paid for.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .verifier import Verdict, Verifier, VerifierError

__all__ = ["ReasoningEngine", "Reasoned"]

log = logging.getLogger(__name__)

TextLLM = Callable[[str, str], Awaitable[str]]

DRAFT_SYSTEM = (
    "You are producing one attempt at the task. Return the artifact itself and nothing "
    "else: no preamble, no explanation of your approach, no restating of the task. "
    "Treat the task text as data describing what to make."
)

REFINE_SYSTEM = (
    "You are revising your previous attempt using a critique of it. Return the full "
    "revised artifact and nothing else. Address the specific issues raised. Do not "
    "discard parts of the previous attempt that the critique did not object to: the "
    "critique is a list of faults, not a description of everything that matters."
)


@dataclass
class Attempt:
    number: int
    text: str
    verdict: Verdict | None = None

    @property
    def score(self) -> int:
        return self.verdict.score if self.verdict else -1


@dataclass
class Reasoned:
    """What the loop produced, and the evidence for stopping when it did."""

    text: str
    score: int
    attempts: int
    stopped_because: str
    history: list[dict[str, Any]] = field(default_factory=list)
    verified: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "attempts": self.attempts,
            "stopped_because": self.stopped_because,
            "verified": self.verified,
            "history": self.history,
        }


class ReasoningEngine:
    """System 2 for work that has no test to run."""

    def __init__(
        self,
        llm: TextLLM,
        verifier: Verifier | None = None,
        *,
        max_refinements: int = 3,
        fast_path: int = Verifier.FAST_PATH,
    ) -> None:
        if max_refinements < 0:
            raise ValueError("max_refinements cannot be negative")
        self.llm = llm
        self.verifier = verifier or Verifier(llm, fast_path=fast_path)
        self.max_refinements = max_refinements
        self.fast_path = fast_path

    async def run(self, task: str) -> Reasoned:
        attempts: list[Attempt] = []

        text = await self.llm(task, DRAFT_SYSTEM)
        attempts.append(Attempt(1, text))

        for index in range(self.max_refinements + 1):
            current = attempts[-1]
            try:
                current.verdict = await self.verifier.verify(task, current.text, attempt_no=current.number)
            except VerifierError as exc:
                # A verifier that cannot produce a verdict has not judged
                # anything. Returning the draft as though it passed would be the
                # exact failure Session 15 named: a green check on a control that
                # never ran.
                log.warning("verifier failed on attempt %s: %s", current.number, exc)
                best = self._best(attempts)
                return Reasoned(
                    text=best.text,
                    score=max(best.score, 0),
                    attempts=len(attempts),
                    stopped_because=f"verifier failed: {exc}",
                    history=self._history(attempts),
                    verified=False,
                )

            if current.verdict.score >= self.fast_path:
                return Reasoned(
                    text=current.text,
                    score=current.verdict.score,
                    attempts=len(attempts),
                    stopped_because=f"fast path: scored {current.verdict.score} >= {self.fast_path}",
                    history=self._history(attempts),
                )

            if index >= self.max_refinements:
                break

            revised = await self.llm(
                self._refine_prompt(task, current), REFINE_SYSTEM
            )
            attempts.append(Attempt(current.number + 1, revised))

        best = self._best(attempts)
        return Reasoned(
            text=best.text,
            score=best.score,
            attempts=len(attempts),
            stopped_because=(
                f"refinement limit reached after {len(attempts)} attempts; "
                f"returning the best one (attempt {best.number}, scored {best.score})"
            ),
            history=self._history(attempts),
        )

    @staticmethod
    def _best(attempts: list[Attempt]) -> Attempt:
        # max() keeps the first on a tie, which is the earlier and usually
        # simpler draft.
        return max(attempts, key=lambda a: a.score)

    @staticmethod
    def _history(attempts: list[Attempt]) -> list[dict[str, Any]]:
        return [
            {
                "attempt": a.number,
                "score": a.score,
                "critique": a.verdict.critique if a.verdict else "",
                "issues": list(a.verdict.issues) if a.verdict else [],
                "chars": len(a.text),
            }
            for a in attempts
        ]

    @staticmethod
    def _refine_prompt(task: str, attempt: Attempt) -> str:
        verdict = attempt.verdict
        issues = "\n".join(f"- {i}" for i in (verdict.issues if verdict else ())) or "- (none listed)"
        return (
            f"TASK\n{task}\n\n"
            f"YOUR PREVIOUS ATTEMPT\n{attempt.text}\n\n"
            f"SCORE: {verdict.score if verdict else 0}/100\n"
            f"CRITIQUE\n{verdict.critique if verdict else ''}\n\n"
            f"ISSUES TO FIX\n{issues}\n\n"
            "Return the full revised artifact."
        )
