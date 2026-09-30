"""LLM-as-judge against a GENERIC rubric: did this answer resolve this task?

The one number the session turns on — cost per *resolved* task — needs a verdict,
and the cheap way to get one is a per-task answer key. That is exactly what this
module refuses to do. The rubric is fixed, task-agnostic and config-owned; the
only per-task input is a short ``expectation`` string carried in the task data
file. Point the same judge at a task set nobody has seen and it works unchanged.

Four properties make the verdict something a lecture can lean on:

**Independence.** The judge is a panel of gateway requests declared in
``evals.yaml``, so it can be pointed at models the answering ladder never uses.
Every verdict records which provider and model judged it and flags
:attr:`Verdict.self_judged` when a judge graded its own model's output. The flag
is not enforcement — self-judging is sometimes unavoidable — it is disclosure.

**Disagreement is reported, not hidden.** With more than one panel member the
verdict carries the agreement fraction and a ``disputed`` flag, and the
configured tie-break decides split panels.

**An unparseable verdict is a JUDGE failure, never a task outcome.** A judge that
returns prose, truncates, or omits a criterion produces
``status="judge_failed"`` and ``resolved=None``. Nothing silently becomes
resolved or unresolved, because both directions would quietly bias the headline
number: counting a judge failure as unresolved inflates the cost per resolved
task, counting it as resolved deflates it.

**An empty or errored answer is unresolved without a call.** There is nothing to
grade, and paying a judge to confirm that would be theatre.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from ..economics.pricing import Pricing
from .config import Criterion, JudgeModel, RubricConfig

#: Gateway ``agent`` tag every judge call carries, so the judge's own meta-cost is
#: separable from the work being judged in any cost rollup.
JUDGE_AGENT = "s17_rubric_judge"

STATUS_RESOLVED = "resolved"
STATUS_UNRESOLVED = "unresolved"
STATUS_JUDGE_FAILED = "judge_failed"

_FENCE_OPEN = re.compile(r"^```[a-zA-Z0-9_-]*\n?")
_FENCE_CLOSE = re.compile(r"\n?```\s*$")


class JudgeUnparseable(RuntimeError):
    """The judge's reply could not be read as a rubric verdict.

    Raised by :func:`parse_scores` and recorded per sample. It never becomes a
    task outcome.
    """


def _json_object(text: str) -> dict[str, Any] | None:
    """The JSON object in a model reply, tolerating fences and surrounding prose."""
    if not isinstance(text, str):
        return None
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = _FENCE_CLOSE.sub("", _FENCE_OPEN.sub("", candidate))
    try:
        parsed = json.loads(candidate)
    except Exception:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(candidate[start : end + 1])
        except Exception:
            return None
    return parsed if isinstance(parsed, dict) else None


def parse_scores(
    text: str, criteria: tuple[Criterion, ...], scale_max: float
) -> tuple[dict[str, float], str, list[str]]:
    """Read a rubric verdict out of a judge reply, or raise.

    Deliberately strict about structure and forgiving about range: a missing or
    non-numeric criterion is a judge failure, because guessing it would invent the
    verdict, while a score outside the configured scale is clamped and the clamp
    is reported. Returns ``(scores, notes, warnings)``.
    """
    payload = _json_object(text)
    if payload is None:
        raise JudgeUnparseable("no JSON object found in the judge reply")
    raw = payload.get("scores")
    if not isinstance(raw, dict):
        raise JudgeUnparseable("judge reply has no 'scores' object")

    scores: dict[str, float] = {}
    warnings: list[str] = []
    for criterion in criteria:
        if criterion.name not in raw:
            raise JudgeUnparseable(f"judge reply is missing criterion {criterion.name!r}")
        value = raw[criterion.name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            try:
                value = float(str(value).strip())
            except Exception as error:
                raise JudgeUnparseable(
                    f"criterion {criterion.name!r} is not a number: {value!r}"
                ) from error
        clamped = min(max(float(value), 0.0), float(scale_max))
        if clamped != float(value):
            warnings.append(f"{criterion.name} {value} clamped to {clamped}")
        scores[criterion.name] = clamped
    notes = payload.get("notes")
    return scores, ("" if notes is None else str(notes))[:600], warnings


@dataclass(frozen=True)
class CriterionScore:
    """One rubric axis for one verdict: the panel mean, and how it weighed."""

    name: str
    score: float
    normalized: float
    weight: float

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "score": self.score,
                "normalized": round(self.normalized, 4), "weight": round(self.weight, 4)}


@dataclass(frozen=True)
class JudgeSample:
    """One panel member's grading of one answer."""

    judge: str
    ok: bool
    #: Whether a provider actually answered. False when the transport itself raised.
    called: bool = False
    requested_provider: str | None = None
    requested_model: str | None = None
    provider: str | None = None
    model: str | None = None
    scores: dict[str, float] = field(default_factory=dict)
    overall: float | None = None
    resolved: bool | None = None
    reason: str = ""
    notes: str = ""
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    raw: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    latency_ms: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "judge": self.judge, "ok": self.ok, "called": self.called,
            "requested": {"provider": self.requested_provider, "model": self.requested_model},
            "answered_by": {"provider": self.provider, "model": self.model},
            "scores": self.scores, "overall": None if self.overall is None else round(self.overall, 4),
            "resolved": self.resolved, "reason": self.reason, "notes": self.notes,
            "warnings": list(self.warnings), "error": self.error,
            "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
            "cost": self.cost, "latency_ms": self.latency_ms,
            "raw": self.raw[:1200],
        }


@dataclass(frozen=True)
class Verdict:
    """What the panel concluded, and everything needed to distrust it."""

    task_id: str
    status: str
    resolved: bool | None
    overall: float | None
    threshold: float
    reason: str
    criteria: tuple[CriterionScore, ...] = ()
    samples: tuple[JudgeSample, ...] = ()
    agreement: float | None = None
    disputed: bool = False
    judge_calls: int = 0
    judge_failures: int = 0
    judge_cost: float = 0.0
    judge_input_tokens: int = 0
    judge_output_tokens: int = 0
    judged_by: tuple[str, ...] = ()
    answer_provider: str | None = None
    answer_model: str | None = None
    self_judged: bool = False
    expectation_used: bool = False

    @property
    def failed(self) -> bool:
        """True when the judge could not produce a verdict at all."""
        return self.status == STATUS_JUDGE_FAILED

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id, "status": self.status, "resolved": self.resolved,
            "overall": None if self.overall is None else round(self.overall, 4),
            "threshold": self.threshold, "reason": self.reason,
            "criteria": [criterion.as_dict() for criterion in self.criteria],
            "agreement": self.agreement, "disputed": self.disputed,
            "judge_calls": self.judge_calls, "judge_failures": self.judge_failures,
            "judge_cost": self.judge_cost,
            "judge_tokens": {"input": self.judge_input_tokens, "output": self.judge_output_tokens},
            "judged_by": list(self.judged_by),
            "answer": {"provider": self.answer_provider, "model": self.answer_model},
            "self_judged": self.self_judged, "expectation_used": self.expectation_used,
            "samples": [sample.as_dict() for sample in self.samples],
        }


def _same_model(left: str | None, right: str | None) -> bool:
    """Whether two model ids denote the same model, allowing gateway decoration."""
    if not left or not right:
        return False
    a, b = left.strip().lower(), right.strip().lower()
    return a == b or a.startswith(b) or b.startswith(a)


class RubricJudge:
    """The rubric, applied through the same gateway contract the runtime uses.

    ``transport`` is the ordinary :class:`~sourcecode.economics.ChatTransport`: one
    ``chat(prompt=, system=, request=)``. The judge therefore rides the gateway's
    own routing, quotas, retries and ledger, and holds no credential — the same
    boundary every other model call in this codebase respects.
    """

    def __init__(
        self,
        transport: Any,
        rubric: RubricConfig,
        *,
        pricing: Pricing | None = None,
        panel: tuple[JudgeModel, ...] | None = None,
    ) -> None:
        self.transport = transport
        self.rubric = rubric
        self.pricing = pricing
        self.panel = tuple(panel) if panel else rubric.panel
        if not self.panel:
            raise ValueError("a judge needs at least one panel member")
        #: Running meta-cost of judging, so it is never confused with the work.
        self.calls = 0
        self.failures = 0
        self.transport_failures = 0
        self.cost = 0.0
        self.input_tokens = 0
        self.output_tokens = 0
        self._last_call_at = 0.0

    async def _pace(self) -> None:
        """Hold the configured gap between judge calls (free-tier quotas are small)."""
        gap = self.rubric.pace_seconds
        if gap <= 0:
            return
        wait = gap - (time.monotonic() - self._last_call_at)
        if wait > 0 and self._last_call_at:
            await asyncio.sleep(wait)
        self._last_call_at = time.monotonic()

    # --- prompt ------------------------------------------------------------ #

    def schema(self, criteria: tuple[Criterion, ...]) -> dict[str, Any]:
        """The structured-output schema for this task's applicable criteria."""
        return {
            "type": "json_schema",
            "name": "rubric_verdict",
            "schema": {
                "type": "object",
                "properties": {
                    "scores": {
                        "type": "object",
                        "properties": {c.name: {"type": "integer"} for c in criteria},
                        "required": [c.name for c in criteria],
                    },
                    "notes": {"type": "string"},
                },
                "required": ["scores", "notes"],
            },
        }

    def instruction(
        self, *, task: str, answer: str, expectation: str | None, criteria: tuple[Criterion, ...]
    ) -> str:
        """The judge's user message: a JSON envelope, so nothing reads as a command."""
        return json.dumps(
            {
                "task_given_to_the_answerer": task[: self.rubric.max_task_chars],
                "answer_under_review": answer[: self.rubric.max_answer_chars],
                "success_criterion": expectation or None,
                "rubric": [{"criterion": c.name, "meaning": c.description} for c in criteria],
                "scale": {"min": 0, "max": self.rubric.scale_max, "integers_only": True},
                "return_exactly": {
                    "scores": {c.name: "<integer>" for c in criteria},
                    "notes": "<= 40 words of justification",
                },
            },
            ensure_ascii=False,
        )

    # --- one panel member -------------------------------------------------- #

    async def _sample(
        self,
        member: JudgeModel,
        *,
        prompt: str,
        criteria: tuple[Criterion, ...],
    ) -> JudgeSample:
        request = {
            **member.request,
            "response_format": self.schema(criteria),
            "agent": member.request.get("agent", JUDGE_AGENT),
        }
        base = {
            "judge": member.name,
            "requested_provider": member.provider,
            "requested_model": member.model,
        }
        # A rate limit or a restarting gateway is a TRANSPORT failure, not a judge
        # failure: the judge never saw the answer. Retrying with backoff is the
        # honest response; giving up and calling the task unresolved would not be.
        response: dict[str, Any] | None = None
        last_error = ""
        for attempt in range(self.rubric.retries + 1):
            await self._pace()
            try:
                response = await self.transport.chat(
                    prompt=prompt, system=self.rubric.system_preamble, request=request
                )
                break
            except Exception as error:
                last_error = f"{type(error).__name__}: {error}"
                self.transport_failures += 1
                if attempt < self.rubric.retries and self.rubric.retry_backoff_seconds > 0:
                    await asyncio.sleep(self.rubric.retry_backoff_seconds * (attempt + 1))
        if response is None:
            self.failures += 1
            return JudgeSample(ok=False, error=last_error or "transport returned nothing", **base)

        self.calls += 1
        text = str(response.get("text") or "")
        input_tokens = int(response.get("input_tokens") or 0)
        output_tokens = int(response.get("output_tokens") or 0)
        cost = 0.0
        if self.pricing is not None:
            cost = self.pricing.cost(
                response.get("model") or member.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=int(response.get("cache_read_input_tokens") or 0),
                cache_write_tokens=int(response.get("cache_creation_input_tokens") or 0),
            )
        self.cost += cost
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        usage = {
            "called": True,
            "provider": response.get("provider"), "model": response.get("model"),
            "input_tokens": input_tokens, "output_tokens": output_tokens, "cost": cost,
            "latency_ms": response.get("latency_ms"), "raw": text,
        }
        try:
            scores, notes, warnings = parse_scores(text, criteria, self.rubric.scale_max)
        except JudgeUnparseable as error:
            self.failures += 1
            return JudgeSample(ok=False, error=str(error), **base, **usage)

        overall = self.rubric.overall(scores, criteria)
        resolved, reason = self.rubric.resolved(overall, scores, criteria)
        return JudgeSample(
            ok=True, scores=scores, overall=overall, resolved=resolved, reason=reason,
            notes=notes, warnings=warnings, **base, **usage,
        )

    # --- the verdict ------------------------------------------------------- #

    async def judge(
        self,
        *,
        task: str,
        answer: str | None,
        expectation: str | None = None,
        task_id: str = "task",
        answer_provider: str | None = None,
        answer_model: str | None = None,
        error: str | None = None,
    ) -> Verdict:
        """Grade one answer. Never raises for a bad answer or a bad judge reply."""
        criteria = self.rubric.applicable(has_expectation=bool((expectation or "").strip()))
        weights = self.rubric.weights(criteria)
        shared = {
            "task_id": task_id,
            "threshold": self.rubric.threshold,
            "answer_provider": answer_provider,
            "answer_model": answer_model,
            "expectation_used": bool((expectation or "").strip()),
        }

        # An empty or errored answer resolves nothing, and needs no judge to say so.
        if error or not (answer or "").strip():
            return Verdict(
                status=STATUS_UNRESOLVED, resolved=False, overall=0.0,
                reason=f"answer failed: {error}" if error else "answer is empty",
                criteria=tuple(
                    CriterionScore(c.name, 0.0, 0.0, weights[c.name]) for c in criteria
                ),
                **shared,
            )

        prompt = self.instruction(
            task=task, answer=answer or "", expectation=expectation, criteria=criteria
        )
        samples = tuple(
            [await self._sample(member, prompt=prompt, criteria=criteria) for member in self.panel]
        )
        usable = [sample for sample in samples if sample.ok and sample.overall is not None]
        judged_by = tuple(
            f"{sample.provider or sample.requested_provider}/{sample.model or sample.requested_model}"
            for sample in samples
        )
        self_judged = any(
            _same_model(sample.model or sample.requested_model, answer_model) for sample in samples
        )
        totals = {
            "samples": samples,
            "judge_calls": sum(1 for sample in samples if sample.called),
            "judge_failures": sum(1 for sample in samples if not sample.ok),
            "judge_cost": sum(sample.cost for sample in samples),
            "judge_input_tokens": sum(sample.input_tokens for sample in samples),
            "judge_output_tokens": sum(sample.output_tokens for sample in samples),
            "judged_by": judged_by,
            "self_judged": self_judged,
        }

        # Every panel member failed: there is no verdict, and pretending otherwise
        # would bias the headline number in one direction or the other.
        if not usable:
            reasons = "; ".join(sample.error or "unknown" for sample in samples) or "no judge replied"
            return Verdict(
                status=STATUS_JUDGE_FAILED, resolved=None, overall=None,
                reason=f"no usable verdict from {len(samples)} judge(s): {reasons}",
                criteria=(), **totals, **shared,
            )

        mean_scores = {
            criterion.name: sum(sample.scores[criterion.name] for sample in usable) / len(usable)
            for criterion in criteria
        }
        mean_overall = sum(sample.overall or 0.0 for sample in usable) / len(usable)
        votes = [bool(sample.resolved) for sample in usable]
        for_resolved = sum(votes)
        against = len(votes) - for_resolved
        disputed = bool(for_resolved and against)

        if for_resolved > against:
            resolved, reason = True, f"{for_resolved}/{len(votes)} judges resolved"
        elif against > for_resolved:
            resolved, reason = False, f"{against}/{len(votes)} judges did not resolve"
        elif self.rubric.tie_break == "unresolved":
            resolved, reason = False, f"panel split {for_resolved}/{len(votes)}; tie_break=unresolved"
        else:
            resolved, floor_reason = self.rubric.resolved(mean_overall, mean_scores, criteria)
            reason = f"panel split {for_resolved}/{len(votes)}; tie_break=score: {floor_reason}"
        agreement = max(for_resolved, against) / len(votes)

        return Verdict(
            status=STATUS_RESOLVED if resolved else STATUS_UNRESOLVED,
            resolved=resolved, overall=mean_overall, reason=reason,
            criteria=tuple(
                CriterionScore(
                    c.name, mean_scores[c.name], self.rubric.normalise(mean_scores[c.name]), weights[c.name]
                )
                for c in criteria
            ),
            agreement=agreement, disputed=disputed, **totals, **shared,
        )

    def meter(self) -> dict[str, Any]:
        """The judge's own meta-cost. LLM-as-judge is not free; report it."""
        return {
            "judge_calls": self.calls,
            "judge_failures": self.failures,
            "judge_transport_failures": self.transport_failures,
            "judge_cost": self.cost,
            "judge_input_tokens": self.input_tokens,
            "judge_output_tokens": self.output_tokens,
            "panel": [
                {"name": member.name, "provider": member.provider, "model": member.model}
                for member in self.panel
            ],
        }
