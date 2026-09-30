"""Did the answer RESOLVE the task? A generic rubric, never a per-task answer key.

Cost-per-*call* is arithmetic. Cost-per-*resolved-task* needs somebody to say
whether a task was resolved, and that is the reason this proof was deferred: the
obvious way to decide it is to write down the right answer for each task, which
bakes a use case into the library and measures nothing a reviewer could reuse.

So the judgement is split in two:

* the **rubric** is fixed, generic and config-owned (:mod:`sourcecode.evals.config`).
  Every criterion is a property of an answer-to-a-task pair — did it address what
  was asked, is it specific, is it self-consistent, is it complete enough to act
  on — and holds for a task nobody has seen.
* the **task** is data (:mod:`sourcecode.evals.tasks`). A task file may carry a short
  natural-language ``expectation``; the judge scores against whatever text the
  file supplies and never against anything compiled into Python.

:mod:`sourcecode.evals.judge` runs that rubric through the same gateway contract the
runtime uses, on a panel of models named in config, and reports what it could not
parse instead of guessing.
"""

from .config import Criterion, EvalsConfig, JudgeModel, RubricConfig, StrategyPolicy
from .judge import (
    JUDGE_AGENT,
    CriterionScore,
    JudgeSample,
    JudgeUnparseable,
    RubricJudge,
    Verdict,
    parse_scores,
)
from .pairs import (
    POSITIVE_LABEL,
    LabelledPair,
    Operating,
    best_operating,
    by_family,
    load_pairs,
    separable,
    steepest_fpr_drop,
    sweep,
    thresholds,
)
from .tasks import EvalTask, load_tasks

__all__ = [
    "Criterion",
    "CriterionScore",
    "EvalTask",
    "EvalsConfig",
    "JUDGE_AGENT",
    "JudgeModel",
    "JudgeSample",
    "JudgeUnparseable",
    "LabelledPair",
    "Operating",
    "POSITIVE_LABEL",
    "RubricConfig",
    "RubricJudge",
    "StrategyPolicy",
    "Verdict",
    "best_operating",
    "by_family",
    "load_pairs",
    "load_tasks",
    "parse_scores",
    "separable",
    "steepest_fpr_drop",
    "sweep",
    "thresholds",
]
