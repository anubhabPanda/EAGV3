"""The judge is the load-bearing part of p1, so it is tested like one.

Cost per resolved task is only as trustworthy as the thing that says "resolved".
These tests pin the properties that make the verdict usable in a lecture:

* the rubric, the weights and the bar come from config, not from Python;
* an unparseable judge reply is a JUDGE failure and never a task outcome;
* an empty or errored answer is unresolved without paying for a judge call;
* a task file with invented criteria works, because the rubric is generic;
* panel disagreement is reported rather than smoothed away.

Nothing here talks to a network. The transport is a stub, which is the point: the
judge's contract is one ``chat(prompt=, system=, request=)`` call.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from sourcecode.evals import (
    EvalsConfig,
    JudgeModel,
    JudgeUnparseable,
    RubricJudge,
    load_tasks,
    parse_scores,
)
from sourcecode.evals.judge import STATUS_JUDGE_FAILED, STATUS_RESOLVED, STATUS_UNRESOLVED

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
TASKS_FILE = Path(__file__).resolve().parents[1] / "proofs" / "tasks" / "mixed.jsonl"


def _string_literals(package: Path) -> set[str]:
    """Every string literal in a package, docstrings excluded.

    Prose in a docstring is not hardcoding; a quoted criterion name in the code is.
    Comparing against literals rather than raw text keeps that distinction honest.
    """
    import ast

    found: set[str] = set()
    for path in sorted(package.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {
            ast.get_docstring(node)
            for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value not in docstrings:
                found.add(node.value)
    return found


# --------------------------------------------------------------------------- #
# stub transports
# --------------------------------------------------------------------------- #


class ScriptedJudge:
    """Returns the next scripted reply, and records what it was asked."""

    def __init__(self, *replies: str | Exception, tokens: tuple[int, int] = (100, 40)) -> None:
        self.replies = list(replies)
        self.requests: list[dict] = []
        self.prompts: list[str] = []
        self.systems: list[str] = []
        self.input_tokens, self.output_tokens = tokens

    async def chat(self, *, prompt, system, request=None):
        self.prompts.append(prompt)
        self.systems.append(system)
        self.requests.append(dict(request or {}))
        reply = self.replies.pop(0) if self.replies else self.replies_exhausted()
        if isinstance(reply, Exception):
            raise reply
        return {
            "text": reply, "provider": (request or {}).get("provider"),
            "model": (request or {}).get("model"),
            "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
            "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0, "latency_ms": 3.0,
        }

    @staticmethod
    def replies_exhausted() -> str:
        raise AssertionError("the judge made more calls than the test scripted")


def verdict_json(**scores: int) -> str:
    full = {"addresses_task": 4, "specific": 4, "consistent": 4, "complete": 4, "meets_expectation": 4}
    full.update(scores)
    return json.dumps({"scores": full, "notes": "scripted"})


def rubric(**overrides):
    config = EvalsConfig.load(CONFIG_DIR)
    if not overrides:
        return config.rubric
    from dataclasses import replace

    return replace(config.rubric, **overrides)


def one_judge(*replies, **overrides):
    transport = ScriptedJudge(*replies)
    member = JudgeModel("stub", {"provider": "stub_provider", "model": "stub-model"})
    return transport, RubricJudge(transport, rubric(**overrides), panel=(member,))


# --------------------------------------------------------------------------- #
# the rubric and the bar are CONFIG
# --------------------------------------------------------------------------- #


def test_rubric_threshold_and_weights_come_from_the_config_file():
    raw = yaml.safe_load((CONFIG_DIR / "evals.yaml").read_text(encoding="utf-8"))
    loaded = EvalsConfig.load(CONFIG_DIR).rubric
    assert loaded.threshold == raw["judge"]["threshold"]
    assert loaded.min_criterion == raw["judge"]["min_criterion"]
    assert loaded.scale_max == raw["judge"]["scale_max"]
    assert [c.name for c in loaded.criteria] == [row["name"] for row in raw["judge"]["criteria"]]
    assert [c.weight for c in loaded.criteria] == [row.get("weight", 1.0) for row in raw["judge"]["criteria"]]
    # No criterion name and no judge model is written anywhere in the library:
    # rename one in the file and nothing needs recompiling. That the BAR is config
    # too is shown by test_moving_the_threshold_in_config_changes_the_verdict.
    literals = _string_literals(Path(__file__).resolve().parents[1] / "sourcecode" / "evals")
    for criterion in loaded.criteria:
        assert criterion.name not in literals, f"{criterion.name} is hardcoded in the judge"
    for member in loaded.panel:
        assert member.model not in literals, "the judge names a model in Python"
        assert member.provider not in literals, "the judge names a provider in Python"


def test_moving_the_threshold_in_config_changes_the_verdict():
    scores = {"addresses_task": 4, "specific": 3, "consistent": 3, "complete": 3, "meets_expectation": 3}
    strict, lenient = rubric(threshold=0.95), rubric(threshold=0.5)
    criteria = strict.applicable(has_expectation=True)
    overall = strict.overall(scores, criteria)
    assert strict.resolved(overall, scores, criteria)[0] is False
    assert lenient.resolved(overall, scores, criteria)[0] is True


def test_a_criterion_floor_stops_a_good_average_hiding_a_zero():
    """A fluent, complete answer to the WRONG question must not clear the bar."""
    bar = rubric(threshold=0.5, min_criterion=0.5)
    scores = {"addresses_task": 0, "specific": 4, "consistent": 4, "complete": 4, "meets_expectation": 4}
    criteria = bar.applicable(has_expectation=True)
    overall = bar.overall(scores, criteria)
    assert overall >= bar.threshold
    resolved, reason = bar.resolved(overall, scores, criteria)
    assert resolved is False
    assert "addresses_task" in reason


def test_criteria_needing_an_expectation_are_dropped_and_weights_renormalised():
    bar = rubric()
    with_expectation = bar.applicable(has_expectation=True)
    without = bar.applicable(has_expectation=False)
    assert len(without) == len(with_expectation) - 1
    assert all(not c.requires_expectation for c in without)
    assert pytest.approx(sum(bar.weights(without).values())) == 1.0
    assert pytest.approx(sum(bar.weights(with_expectation).values())) == 1.0


def test_strategy_retry_policy_comes_from_config():
    raw = yaml.safe_load((CONFIG_DIR / "evals.yaml").read_text(encoding="utf-8"))["strategies"]
    policy = EvalsConfig.load(CONFIG_DIR).strategies
    assert policy.cheapest_retries == raw["cheapest_retries"]
    assert policy.max_attempts == raw["max_attempts"]
    assert policy.cheapest_attempts == min(raw["max_attempts"], 1 + raw["cheapest_retries"])


def test_a_config_with_only_expectation_criteria_is_rejected():
    config = EvalsConfig.from_mapping({
        "judge": {
            "criteria": [{"name": "only", "requires_expectation": True, "description": "x"}],
            "panel": [{"name": "j", "request": {"provider": "p", "model": "m"}}],
            "system_preamble": "grade it",
        }
    })
    with pytest.raises(ValueError, match="without expectations"):
        config.rubric.applicable(has_expectation=False)


# --------------------------------------------------------------------------- #
# parsing: strict about structure, loud about failure
# --------------------------------------------------------------------------- #


def test_parse_scores_reads_fenced_json_and_ignores_surrounding_prose():
    criteria = rubric().applicable(has_expectation=True)
    fenced = "Here is my verdict:\n```json\n" + verdict_json(specific=2) + "\n```\nHope that helps."
    scores, notes, warnings = parse_scores(fenced, criteria, 4)
    assert scores["specific"] == 2.0
    assert notes == "scripted"
    assert warnings == []


@pytest.mark.parametrize("reply", [
    "The answer looks pretty good to me, I'd say about a 3 out of 4.",
    '{"notes": "no scores object"}',
    '{"scores": {"addresses_task": 4}, "notes": "missing the rest"}',
    '{"scores": {"addresses_task": "excellent", "specific": 4, "consistent": 4, '
    '"complete": 4, "meets_expectation": 4}}',
    "",
    '{"scores": [4, 4, 4, 4, 4]}',
])
def test_unparseable_judge_replies_raise_rather_than_guess(reply):
    criteria = rubric().applicable(has_expectation=True)
    with pytest.raises(JudgeUnparseable):
        parse_scores(reply, criteria, 4)


def test_out_of_range_scores_are_clamped_and_the_clamp_is_reported():
    criteria = rubric().applicable(has_expectation=True)
    scores, _, warnings = parse_scores(verdict_json(specific=9, complete=-3), criteria, 4)
    assert scores["specific"] == 4.0 and scores["complete"] == 0.0
    assert len(warnings) == 2


async def test_an_unparseable_verdict_is_a_judge_failure_not_a_task_outcome():
    transport, judge = one_judge("I think it is fine, roughly a three.")
    verdict = await judge.judge(task="anything", answer="an answer", expectation="something")
    assert verdict.status == STATUS_JUDGE_FAILED
    assert verdict.resolved is None, "a judge failure must never be counted either way"
    assert verdict.overall is None
    assert verdict.failed is True
    assert verdict.judge_failures == 1
    assert judge.failures == 1
    assert "no JSON object" in verdict.samples[0].error
    # The raw reply is kept so a reviewer can see what the judge actually said.
    assert "roughly a three" in verdict.samples[0].raw


async def test_a_transport_failure_is_retried_then_reported_as_a_judge_failure():
    transport = ScriptedJudge(RuntimeError("429 rate limited"), verdict_json())
    member = JudgeModel("stub", {"provider": "p", "model": "m"})
    judge = RubricJudge(transport, rubric(retries=1, retry_backoff_seconds=0.0), panel=(member,))
    verdict = await judge.judge(task="t", answer="a", expectation="e")
    assert verdict.status == STATUS_RESOLVED, "a rate limit is a transport failure, so retry"
    assert judge.transport_failures == 1
    assert judge.failures == 0

    transport = ScriptedJudge(RuntimeError("boom"))
    judge = RubricJudge(transport, rubric(retries=0), panel=(member,))
    verdict = await judge.judge(task="t", answer="a", expectation="e")
    assert verdict.status == STATUS_JUDGE_FAILED and verdict.resolved is None


# --------------------------------------------------------------------------- #
# answers that need no judge
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("answer", ["", "   ", "\n\t ", None])
async def test_an_empty_answer_is_unresolved_without_paying_a_judge(answer):
    transport, judge = one_judge()
    verdict = await judge.judge(task="anything", answer=answer, expectation="something")
    assert verdict.status == STATUS_UNRESOLVED
    assert verdict.resolved is False
    assert verdict.overall == 0.0
    assert verdict.judge_calls == 0 and judge.calls == 0
    assert transport.requests == [], "no judge call should have been made"


async def test_an_errored_answer_is_unresolved_and_says_why():
    transport, judge = one_judge()
    verdict = await judge.judge(task="t", answer="partial text", error="budget refused a call")
    assert verdict.resolved is False
    assert "budget refused" in verdict.reason
    assert transport.requests == []


# --------------------------------------------------------------------------- #
# a fabricated, never-before-seen task file
# --------------------------------------------------------------------------- #


async def test_an_invented_task_file_with_invented_criteria_works_unchanged(tmp_path):
    """The generic-rubric claim, tested: a domain nobody anticipated, no code edit."""
    invented = tmp_path / "invented.jsonl"
    invented.write_text(
        "# a domain no sourcecode module has heard of\n"
        + json.dumps({"id": "z1", "difficulty": "silly",
                      "task": "Name the ceremonial fruit of the Grand Duchy of Fenwick.",
                      "expectation": "Names the quince and says the coronation is in spring."}) + "\n"
        + json.dumps({"id": "z2", "task": "How many moons does Fenwick claim?"}) + "\n",
        encoding="utf-8",
    )
    tasks = load_tasks(invented)
    assert [task.id for task in tasks] == ["z1", "z2"]
    assert tasks[0].difficulty == "silly"
    assert tasks[1].has_expectation is False

    transport, judge = one_judge(verdict_json(), verdict_json(specific=1))
    first = await judge.judge(task=tasks[0].task, answer="The quince; crowned each spring.",
                              expectation=tasks[0].expectation, task_id=tasks[0].id)
    assert first.status == STATUS_RESOLVED and first.expectation_used is True
    # The invented criterion text reached the judge as DATA, and only as data.
    assert "quince" in transport.prompts[0]
    assert "quince" not in transport.systems[0]

    second = await judge.judge(task=tasks[1].task, answer="Nobody knows.", task_id=tasks[1].id)
    assert second.expectation_used is False
    assert "meets_expectation" not in [criterion.name for criterion in second.criteria]
    assert second.resolved is False


def test_the_shipped_task_file_is_data_and_spans_difficulty():
    tasks = load_tasks(TASKS_FILE)
    assert len(tasks) >= 8
    assert all(task.task.strip() for task in tasks)
    assert all(task.has_expectation for task in tasks), "every shipped task states its criterion"
    labels = {task.difficulty for task in tasks}
    assert len(labels) >= 3, f"a single-difficulty set measures nothing: {labels}"
    # No task text or expectation appears anywhere in the library.
    library = Path(__file__).resolve().parents[1] / "sourcecode"
    sources = "\n".join(path.read_text(encoding="utf-8") for path in library.rglob("*.py"))
    for task in tasks:
        assert task.task[:40] not in sources
        assert (task.expectation or "@@")[:40] not in sources


@pytest.mark.parametrize("suffix,dump", [
    (".json", lambda rows: json.dumps(rows)),
    (".json", lambda rows: json.dumps({"tasks": rows})),
    (".yaml", lambda rows: yaml.safe_dump(rows)),
])
def test_a_reviewer_may_bring_json_or_yaml(tmp_path, suffix, dump):
    rows = [{"id": "a", "task": "do a thing", "expectation": "the thing is done"}]
    path = tmp_path / f"set{suffix}"
    path.write_text(dump(rows), encoding="utf-8")
    assert load_tasks(path)[0].task == "do a thing"


def test_a_broken_task_file_is_rejected_rather_than_silently_shortened(tmp_path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("# only a comment\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no tasks"):
        load_tasks(empty)

    blank = tmp_path / "blank.jsonl"
    blank.write_text(json.dumps({"id": "x", "task": "   "}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no non-empty 'task'"):
        load_tasks(blank)

    dupes = tmp_path / "dupes.jsonl"
    dupes.write_text("\n".join(json.dumps({"id": "same", "task": f"t{i}"}) for i in range(2)), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate task ids"):
        load_tasks(dupes)

    with pytest.raises(FileNotFoundError):
        load_tasks(tmp_path / "nope.jsonl")


# --------------------------------------------------------------------------- #
# the panel: independence and disagreement
# --------------------------------------------------------------------------- #


async def test_self_judging_is_recorded_rather_than_silently_allowed():
    member = JudgeModel("stub", {"provider": "p", "model": "shared-model"})
    transport = ScriptedJudge(verdict_json(), verdict_json())
    judge = RubricJudge(transport, rubric(), panel=(member,))

    graded_by_itself = await judge.judge(task="t", answer="a", expectation="e",
                                         answer_model="shared-model", answer_provider="p")
    assert graded_by_itself.self_judged is True
    assert graded_by_itself.judged_by == ("p/shared-model",)

    independent = await judge.judge(task="t", answer="a", expectation="e",
                                    answer_model="some-other-model", answer_provider="q")
    assert independent.self_judged is False


async def test_panel_agreement_and_dispute_are_reported():
    panel = (
        JudgeModel("j1", {"provider": "p1", "model": "m1"}),
        JudgeModel("j2", {"provider": "p2", "model": "m2"}),
    )
    # Both judges resolve: unanimous.
    transport = ScriptedJudge(verdict_json(), verdict_json())
    judge = RubricJudge(transport, rubric(), panel=panel)
    agreed = await judge.judge(task="t", answer="a", expectation="e")
    assert agreed.agreement == 1.0 and agreed.disputed is False and agreed.resolved is True
    assert agreed.judge_calls == 2 and len(agreed.judged_by) == 2

    # One resolves, one does not: a split panel, settled by the configured tie-break.
    transport = ScriptedJudge(verdict_json(), verdict_json(meets_expectation=0))
    by_score = RubricJudge(transport, rubric(tie_break="score"), panel=panel)
    split = await by_score.judge(task="t", answer="a", expectation="e")
    assert split.disputed is True and split.agreement == 0.5
    assert "tie_break=score" in split.reason

    transport = ScriptedJudge(verdict_json(), verdict_json(meets_expectation=0))
    conservative = RubricJudge(transport, rubric(tie_break="unresolved"), panel=panel)
    strict = await conservative.judge(task="t", answer="a", expectation="e")
    assert strict.resolved is False and "tie_break=unresolved" in strict.reason


async def test_one_dead_panel_member_still_yields_a_verdict_and_is_reported():
    panel = (
        JudgeModel("j1", {"provider": "p1", "model": "m1"}),
        JudgeModel("j2", {"provider": "p2", "model": "m2"}),
    )
    transport = ScriptedJudge(verdict_json(), "not json at all")
    judge = RubricJudge(transport, rubric(), panel=panel)
    verdict = await judge.judge(task="t", answer="a", expectation="e")
    assert verdict.resolved is True
    assert verdict.judge_failures == 1
    assert verdict.agreement == 1.0, "agreement is over the USABLE samples"


# --------------------------------------------------------------------------- #
# the judge's own cost and its request contract
# --------------------------------------------------------------------------- #


async def test_the_judge_forces_structured_output_and_carries_its_config_request():
    transport, judge = one_judge(verdict_json())
    await judge.judge(task="t", answer="a", expectation="e")
    request = transport.requests[0]
    assert request["provider"] == "stub_provider" and request["model"] == "stub-model"
    fmt = request["response_format"]
    assert fmt["type"] == "json_schema"
    required = fmt["schema"]["properties"]["scores"]["required"]
    assert required == [c.name for c in rubric().applicable(has_expectation=True)]
    assert request["agent"], "judge calls are tagged so their meta-cost is separable"


async def test_the_judges_own_meta_cost_is_metered_separately():
    from sourcecode.economics import EconomicsConfig

    pricing = EconomicsConfig.load(CONFIG_DIR).pricing
    member = JudgeModel("stub", {"provider": "p", "model": next(iter(pricing.models))})
    transport = ScriptedJudge(verdict_json(), tokens=(1000, 500))
    judge = RubricJudge(transport, rubric(), pricing=pricing, panel=(member,))
    verdict = await judge.judge(task="t", answer="a", expectation="e")
    meter = judge.meter()
    assert meter["judge_calls"] == 1
    assert meter["judge_input_tokens"] == 1000 and meter["judge_output_tokens"] == 500
    assert verdict.judge_cost == meter["judge_cost"] >= 0.0


async def test_the_answer_is_bounded_before_it_reaches_the_judge():
    transport, judge = one_judge(verdict_json(), **{"max_answer_chars": 50, "max_task_chars": 20})
    await judge.judge(task="T" * 500, answer="A" * 5000, expectation="e")
    envelope = json.loads(transport.prompts[0])
    assert len(envelope["answer_under_review"]) == 50
    assert len(envelope["task_given_to_the_answerer"]) == 20
