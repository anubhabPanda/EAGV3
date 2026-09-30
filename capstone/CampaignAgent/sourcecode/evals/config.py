"""The rubric, the bar and the judge panel — all of it config, none of it Python.

``evals.yaml`` sits in the same directory as ``tiers.yaml``, ``pricing.yaml`` and
``budgets.yaml``, so one ``--config-dir`` swaps the whole economic *and*
evaluative policy together. Nothing in this module names a criterion, a weight, a
threshold, a provider or a model: change the bar, reweight the rubric, add a
criterion or repoint the panel at different models by editing the file.

Two details are load-bearing rather than decorative:

* a criterion may be marked ``requires_expectation``. It is dropped, and the
  remaining weights renormalised, when a task supplies no success criterion — so
  a task file with no ``expectation`` still scores on a comparable 0..1 scale.
* ``min_criterion`` is a floor applied per criterion. A weighted average alone
  lets a fluent, complete, self-consistent answer to the *wrong question* clear
  the bar; the floor stops it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

#: ``config/`` as shipped next to the package — the same directory the economics
#: config uses, deliberately.
DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"

EVALS_FILE = "evals.yaml"

#: How a panel disagreement is settled. ``score`` compares the panel's mean
#: overall score to the threshold; ``unresolved`` takes the conservative reading
#: and calls any split verdict unresolved.
TIE_BREAKS = ("score", "unresolved")


def config_dir(explicit: str | Path | None = None) -> Path:
    """Where the config lives: the argument, then ``S17_CONFIG_DIR``, then default."""
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    from_env = os.getenv("S17_CONFIG_DIR")
    if from_env:
        return Path(from_env).expanduser().resolve()
    return DEFAULT_CONFIG_DIR


@dataclass(frozen=True)
class Criterion:
    """One rubric axis. Generic by construction: it never names a domain."""

    name: str
    description: str
    weight: float = 1.0
    requires_expectation: bool = False


@dataclass(frozen=True)
class JudgeModel:
    """One member of the panel: a name plus the gateway request it expands to.

    Exactly the shape a tier has in ``tiers.yaml``, for the same reason — the
    request body is config, so repointing the judge at another provider or model
    is never a Python edit.
    """

    name: str
    request: dict[str, Any] = field(default_factory=dict)

    @property
    def model(self) -> str | None:
        return self.request.get("model")

    @property
    def provider(self) -> str | None:
        return self.request.get("provider")


@dataclass(frozen=True)
class RubricConfig:
    """The generic rubric and the bar an answer must clear to count as resolved."""

    criteria: tuple[Criterion, ...]
    panel: tuple[JudgeModel, ...]
    system_preamble: str
    scale_max: float = 4.0
    threshold: float = 0.75
    min_criterion: float = 0.0
    tie_break: str = "score"
    max_answer_chars: int = 8000
    max_task_chars: int = 4000
    #: A provider rate limit is a TRANSPORT failure, not a judge failure, so it is
    #: retried with backoff before the sample is written off as unusable. Pacing
    #: keeps a free-tier per-minute quota from being burned in the first seconds.
    retries: int = 0
    retry_backoff_seconds: float = 0.0
    pace_seconds: float = 0.0

    def __post_init__(self) -> None:
        if not self.criteria:
            raise ValueError("evals.yaml judge.criteria must list at least one criterion")
        if not self.panel:
            raise ValueError("evals.yaml judge.panel must list at least one judge")
        if self.scale_max <= 0:
            raise ValueError("evals.yaml judge.scale_max must be positive")
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError("evals.yaml judge.threshold is a normalised score in [0, 1]")
        if not 0.0 <= self.min_criterion <= 1.0:
            raise ValueError("evals.yaml judge.min_criterion is a normalised score in [0, 1]")
        if self.tie_break not in TIE_BREAKS:
            raise ValueError(f"evals.yaml judge.tie_break must be one of {TIE_BREAKS}")
        names = [criterion.name for criterion in self.criteria]
        if len(set(names)) != len(names):
            raise ValueError("evals.yaml judge.criteria names must be unique")

    # --- which criteria apply, and how they weigh ------------------------- #

    def applicable(self, *, has_expectation: bool) -> tuple[Criterion, ...]:
        """The criteria in play for this task.

        A criterion that needs the task file's success criterion is dropped when
        the file supplies none, so a bare ``{"id", "task"}`` record still scores.
        """
        if has_expectation:
            return self.criteria
        applicable = tuple(c for c in self.criteria if not c.requires_expectation)
        if not applicable:
            raise ValueError(
                "every configured criterion requires an expectation, so a task file "
                "without expectations cannot be judged: add one general criterion"
            )
        return applicable

    def weights(self, criteria: tuple[Criterion, ...]) -> dict[str, float]:
        """Configured weights, renormalised over the criteria actually in play."""
        total = sum(max(0.0, c.weight) for c in criteria)
        if total <= 0:
            return {c.name: 1.0 / len(criteria) for c in criteria}
        return {c.name: max(0.0, c.weight) / total for c in criteria}

    def normalise(self, score: float) -> float:
        """A raw rubric score on the configured scale, mapped into [0, 1]."""
        return min(1.0, max(0.0, float(score) / self.scale_max))

    def overall(self, scores: dict[str, float], criteria: tuple[Criterion, ...]) -> float:
        """The weighted, normalised overall score for one set of rubric scores."""
        weights = self.weights(criteria)
        return sum(self.normalise(scores[c.name]) * weights[c.name] for c in criteria)

    def resolved(self, overall: float, scores: dict[str, float], criteria: tuple[Criterion, ...]) -> tuple[bool, str]:
        """Whether this score clears the bar, and why not when it does not."""
        floors = [c.name for c in criteria if self.normalise(scores[c.name]) < self.min_criterion]
        if floors:
            return False, (
                f"criterion floor {self.min_criterion} not met on {', '.join(sorted(floors))} "
                f"(overall {overall:.3f})"
            )
        if overall < self.threshold:
            return False, f"overall {overall:.3f} < threshold {self.threshold}"
        return True, f"overall {overall:.3f} >= threshold {self.threshold}"

    def describe(self) -> dict[str, Any]:
        return {
            "scale_max": self.scale_max,
            "threshold": self.threshold,
            "min_criterion": self.min_criterion,
            "tie_break": self.tie_break,
            "retries": self.retries,
            "retry_backoff_seconds": self.retry_backoff_seconds,
            "pace_seconds": self.pace_seconds,
            "criteria": [
                {"name": c.name, "weight": c.weight, "requires_expectation": c.requires_expectation}
                for c in self.criteria
            ],
            "panel": [
                {"name": j.name, "provider": j.provider, "model": j.model} for j in self.panel
            ],
        }


@dataclass(frozen=True)
class StrategyPolicy:
    """What the compared strategies are allowed to do after an unresolved verdict.

    This is the retry policy that makes the always-cheapest baseline a *trap*
    rather than a straw man: the cheap rung is not asked once and abandoned, it is
    retried the way a real agent retries. Both numbers are config, so a reviewer
    can make the trap milder or harsher and watch the conclusion move.
    """

    max_attempts: int = 3
    cheapest_retries: int = 2
    escalate: bool = True
    #: Which rung the budget-aware strategy opens on. ``cheapest`` and
    #: ``most_capable`` are the two ends of whatever ladder is configured, ``role``
    #: takes the rung ``role_tiers`` declares for the calling role, ``default``
    #: takes ``default_tier``, and any other value is read as an explicit tier
    #: name. Nothing here is a tier name, so the ladder can be rewritten freely.
    start: str = "cheapest"

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("evals.yaml strategies.max_attempts must be at least 1")
        if self.cheapest_retries < 0:
            raise ValueError("evals.yaml strategies.cheapest_retries cannot be negative")

    @property
    def cheapest_attempts(self) -> int:
        """Attempts the always-cheapest baseline gets, bounded by ``max_attempts``."""
        return min(self.max_attempts, 1 + self.cheapest_retries)

    def describe(self) -> dict[str, Any]:
        return {
            "max_attempts": self.max_attempts,
            "cheapest_retries": self.cheapest_retries,
            "cheapest_attempts": self.cheapest_attempts,
            "escalate": self.escalate,
            "start": self.start,
        }


@dataclass(frozen=True)
class EvalsConfig:
    """The loaded rubric and strategy policy, plus where they came from."""

    rubric: RubricConfig
    strategies: StrategyPolicy
    directory: Path = DEFAULT_CONFIG_DIR

    @classmethod
    def load(cls, directory: str | Path | None = None) -> EvalsConfig:
        resolved = config_dir(directory)
        path = resolved / EVALS_FILE
        if not path.exists():
            raise FileNotFoundError(f"evaluation config {EVALS_FILE} not found in {resolved}")
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError(f"{path} must contain a mapping")
        return cls.from_mapping(data, directory=resolved)

    @classmethod
    def from_mapping(cls, data: dict[str, Any], *, directory: Path = DEFAULT_CONFIG_DIR) -> EvalsConfig:
        judge = data.get("judge") or {}
        criteria = tuple(
            Criterion(
                name=str(row["name"]),
                description=str(row.get("description", "")).strip(),
                weight=float(row.get("weight", 1.0)),
                requires_expectation=bool(row.get("requires_expectation", False)),
            )
            for row in (judge.get("criteria") or [])
            if isinstance(row, dict) and row.get("name")
        )
        panel = tuple(
            JudgeModel(name=str(row.get("name") or f"judge_{index + 1}"), request=dict(row.get("request") or {}))
            for index, row in enumerate(judge.get("panel") or [])
            if isinstance(row, dict)
        )
        rubric = RubricConfig(
            criteria=criteria,
            panel=panel,
            system_preamble=str(judge.get("system_preamble", "")).strip(),
            scale_max=float(judge.get("scale_max", 4.0)),
            threshold=float(judge.get("threshold", 0.75)),
            min_criterion=float(judge.get("min_criterion", 0.0)),
            tie_break=str(judge.get("tie_break", "score")),
            max_answer_chars=int(judge.get("max_answer_chars", 8000)),
            max_task_chars=int(judge.get("max_task_chars", 4000)),
            retries=int(judge.get("retries", 0)),
            retry_backoff_seconds=float(judge.get("retry_backoff_seconds", 0.0)),
            pace_seconds=float(judge.get("pace_seconds", 0.0)),
        )
        raw_strategies = data.get("strategies") or {}
        strategies = StrategyPolicy(
            max_attempts=int(raw_strategies.get("max_attempts", 3)),
            cheapest_retries=int(raw_strategies.get("cheapest_retries", 2)),
            escalate=bool(raw_strategies.get("escalate", True)),
            start=str(raw_strategies.get("start", "cheapest")),
        )
        return cls(rubric=rubric, strategies=strategies, directory=directory)

    def describe(self) -> dict[str, Any]:
        return {
            "directory": str(self.directory),
            "judge": self.rubric.describe(),
            "strategies": self.strategies.describe(),
        }
