from __future__ import annotations

import json
from pathlib import Path

import pytest

from sourcecode.capabilities import default_registry
from sourcecode.core.live_graph import Event, GraphSnapshot
from sourcecode.planner import GeneralAgentPlanner


class Replies:
    def __init__(self, *values: dict) -> None:
        self.values = list(values)
        self.prompts: list[dict] = []

    async def __call__(self, prompt: str, _system: str) -> dict:
        self.prompts.append(json.loads(prompt))
        return {"text": json.dumps(self.values.pop(0)), "provider": "test", "model": "planner"}


def snapshot(nodes=None, edges=()):
    return GraphSnapshot("run", False, nodes or {}, tuple(edges))


@pytest.mark.asyncio
async def test_unseen_entities_can_be_decomposed_in_parallel_without_domain_code():
    reply = Replies({"add": [
        {"id": "rust", "capability": "researcher",
         "arguments": {"query": "Rust concurrency model ownership async runtimes", "subject": "Rust"},
         "depends_on": []},
        {"id": "go", "capability": "researcher",
         "arguments": {"query": "Go concurrency model goroutines channels", "subject": "Go"},
         "depends_on": []},
    ], "cancel": [], "finish": False, "reason": "independent evidence can land together"})
    planner = GeneralAgentPlanner(reply, default_registry(),
                                  goal="Research Rust and Go, then compare their concurrency models.",
                                  review_terminal=False)
    patch = await planner.plan(snapshot(), Event(1, "run_started", None, {}))
    assert [task.input["query"] for task in patch.add] == [
        "Rust concurrency model ownership async runtimes", "Go concurrency model goroutines channels"]
    assert not patch.connect


@pytest.mark.asyncio
async def test_future_work_cannot_be_pre_spawned_before_its_inputs_exist():
    reply = Replies(
        {"add": [
            {"id": "search", "capability": "web_search", "arguments": {"query": "reliable sources"},
             "depends_on": []},
            {"id": "fetch", "capability": "fetch_url", "arguments": {"url": "https://invented.invalid"},
             "depends_on": ["search"]},
        ], "cancel": [], "finish": False, "reason": "search then fetch"},
    )
    planner = GeneralAgentPlanner(reply, default_registry(), goal="Find and read reliable sources.",
                                  review_terminal=False)
    patch = await planner.plan(snapshot(), Event(1, "run_started", None, {}))
    assert [task.id for task in patch.add] == ["search"]
    assert planner.history[0]["accepted"] is True
    assert "held future tasks fetch" in patch.reason


@pytest.mark.asyncio
async def test_discovered_urls_can_be_fetched_on_the_next_round():
    nodes = {"search": {"id": "search", "skill": "web_search", "input": {"query": "x"},
                        "metadata": {}, "state": "succeeded",
                        "result": {"hits": [{"url": "https://example.com/a"},
                                             {"url": "https://example.com/b"}]}}}
    reply = Replies({"add": [
        {"id": "fetch_a", "capability": "fetch_url", "arguments": {"url": "https://example.com/a"},
         "depends_on": ["search"]},
        {"id": "fetch_b", "capability": "fetch_url", "arguments": {"url": "https://example.com/b"},
         "depends_on": ["search"]},
    ], "cancel": [], "finish": False, "reason": "fetch concrete URLs returned by search"})
    planner = GeneralAgentPlanner(reply, default_registry(), goal="Read two sources.", review_terminal=False)
    patch = await planner.plan(snapshot(nodes), Event(4, "task_succeeded", "search", nodes["search"]["result"]))
    assert patch.connect == (("search", "fetch_a"), ("search", "fetch_b"))


@pytest.mark.asyncio
async def test_planner_may_expand_from_one_outcome_while_a_sibling_is_running():
    nodes = {
        "a": {"id": "a", "skill": "researcher", "input": {}, "metadata": {},
              "state": "succeeded", "result": {"text": "A"}},
        "b": {"id": "b", "skill": "researcher", "input": {}, "metadata": {},
              "state": "running", "result": None},
    }
    reply = Replies(
        {"add": [{"id": "too_early", "capability": "distiller", "arguments": {"query": "combine"},
                  "depends_on": ["a"]}], "cancel": [], "finish": False, "reason": "partial synthesis"},
        {"add": [], "cancel": [], "finish": False, "reason": "wait for b"},
    )
    planner = GeneralAgentPlanner(reply, default_registry(), goal="Compare A and B", review_terminal=False)
    patch = await planner.plan(snapshot(nodes), Event(4, "task_succeeded", "a", {"text": "A"}))
    assert [task.id for task in patch.add] == ["too_early"]
    assert patch.connect == (("a", "too_early"),)


@pytest.mark.asyncio
async def test_planner_can_add_a_join_that_waits_for_a_running_sibling():
    nodes = {
        "date": {"id": "date", "skill": "current_datetime", "input": {}, "metadata": {},
                 "state": "succeeded", "result": {"date": "2026-08-05"}},
        "research": {"id": "research", "skill": "researcher", "input": {}, "metadata": {},
                     "state": "running", "result": None},
    }
    reply = Replies({"add": [{"id": "join", "capability": "distiller",
        "arguments": {"query": "combine date and research"},
        "depends_on": ["date", "research"]}], "cancel": [], "finish": False,
        "reason": "join when both outcomes exist"})
    planner = GeneralAgentPlanner(reply, default_registry(), goal="Build a dated research plan",
                                  review_terminal=False)
    patch = await planner.plan(snapshot(nodes), Event(5, "task_succeeded", "date", {"date": "2026-08-05"}))
    assert [task.id for task in patch.add] == ["join"]
    assert patch.connect == (("date", "join"), ("research", "join"))


def test_planner_manifest_hides_side_effects_the_run_cannot_execute():
    planner = GeneralAgentPlanner(Replies(), default_registry(), goal="answer safely",
                                  review_terminal=False,
                                  allowed_side_effects={"request_approval"})
    payload = json.loads(planner._prompt(snapshot(), Event(1, "run_started", None, {})))
    names = {item["name"] for item in payload["capabilities"]}
    assert "request_approval" in names
    assert "send_channel_message" not in names
    assert "write_file" not in names
    assert "answer_with_evidence" in names


@pytest.mark.asyncio
async def test_duplicate_terminal_proposal_waits_for_the_terminal_already_running():
    nodes = {
        "distill": {"id": "distill", "skill": "distiller", "input": {}, "metadata": {},
                    "state": "succeeded", "result": {"text": "ready"}},
        "answer": {"id": "answer", "skill": "answer_with_evidence", "input": {"query": "goal"},
                   "metadata": {}, "state": "running", "result": None},
    }
    reply = Replies({"add": [{"id": "answer_again", "capability": "answer_with_evidence",
        "arguments": {"query": "a differently worded goal"}, "depends_on": ["distill"]}],
        "cancel": [], "finish": False, "reason": "answer"})
    planner = GeneralAgentPlanner(reply, default_registry(), goal="goal", review_terminal=False)
    patch = await planner.plan(snapshot(nodes), Event(8, "task_succeeded", "distill", {"text": "ready"}))
    assert not patch.add and not patch.finish
    assert planner.history[-1]["accepted"] is True


@pytest.mark.asyncio
async def test_invalid_partial_replan_never_cancels_useful_work_still_running():
    nodes = {"research": {"id": "research", "skill": "researcher", "input": {}, "metadata": {},
                          "state": "running", "result": None}}
    invalid = {"add": [{"id": "bad", "capability": "invented_tool", "arguments": {},
                        "depends_on": []}], "cancel": [], "finish": False, "reason": "bad"}
    planner = GeneralAgentPlanner(Replies(invalid, invalid), default_registry(), goal="research",
                                  review_terminal=False, repair_attempts=1)
    patch = await planner.plan(snapshot(nodes), Event(4, "task_succeeded", "other", {}))
    assert not patch.finish and not patch.cancel
    assert "failed validation" in patch.reason


@pytest.mark.asyncio
async def test_task_keyed_provider_json_is_normalized_by_capability_schema():
    reply = Replies({
        "research_gmail": {"capability": "researcher",
                           "arguments": {"query": "official Gmail watch recovery"},
                           "depends_on": []},
        "research_github": {"capability": "researcher",
                            "arguments": {"query": "official GitHub webhook redelivery"},
                            "depends_on": []},
        "reason": "independent research",
    })
    planner = GeneralAgentPlanner(reply, default_registry(), goal="Research two event sources",
                                  review_terminal=False)
    patch = await planner.plan(snapshot(), Event(1, "run_started", None, {}))
    assert [(task.id, task.skill) for task in patch.add] == [
        ("research_github", "researcher"), ("research_gmail", "researcher")]


@pytest.mark.asyncio
async def test_capability_prefixed_task_key_is_normalized_without_a_channel_table():
    reply = Replies({"send_channel_message_3": {
        "channel": "future_adapter", "recipient_id": "destination", "text": "done",
    }})
    planner = GeneralAgentPlanner(reply, default_registry(), goal="Send through a discovered adapter",
                                  review_terminal=False,
                                  allowed_side_effects={"send_channel_message"})
    patch = await planner.plan(snapshot(), Event(1, "run_started", None, {}))
    assert [(task.id, task.skill, task.input["channel"]) for task in patch.add] == [
        ("send_channel_message_3", "send_channel_message", "future_adapter")]


@pytest.mark.asyncio
async def test_one_patch_can_cancel_and_replace_equivalent_active_work():
    nodes = {"old": {"id": "old", "skill": "fetch_url",
                     "input": {"url": "https://status.example"}, "metadata": {},
                     "state": "pending", "result": None}}
    reply = Replies({"add": [{"id": "retry", "capability": "fetch_url",
        "arguments": {"url": "https://status.example"}, "depends_on": []}],
        "cancel": ["old"], "finish": False, "reason": "replace a genuinely stuck request"})
    planner = GeneralAgentPlanner(reply, default_registry(), goal="Read status", review_terminal=False)
    patch = await planner.plan(snapshot(nodes), Event(4, "task_succeeded", "other", {}))
    assert [task.id for task in patch.add] == ["retry"]
    assert patch.cancel == ("old",)


@pytest.mark.asyncio
async def test_planner_cannot_guess_that_an_executing_worker_is_stuck():
    nodes = {
        "answer": {"id": "answer", "skill": "answer_with_evidence", "input": {"query": "goal"},
                   "metadata": {}, "state": "running", "result": None},
        "distill": {"id": "distill", "skill": "distiller", "input": {"query": "goal"},
                    "metadata": {}, "state": "succeeded", "result": {"text": "ready"}},
    }
    reply = Replies(
        {"add": [], "cancel": ["answer"], "finish": False,
         "reason": "I think the answer is stuck"},
        {"add": [], "cancel": [], "finish": False,
         "reason": "wait for the executing answer; runtime timeout owns failure"},
    )
    planner = GeneralAgentPlanner(reply, default_registry(), goal="goal", review_terminal=False)
    patch = await planner.plan(snapshot(nodes), Event(7, "task_succeeded", "distill", {}))
    assert not patch.cancel and not patch.finish
    assert planner.history[0]["accepted"] is False


@pytest.mark.asyncio
async def test_unexplained_cancellation_cannot_destroy_running_siblings():
    nodes = {
        "aws": {"id": "aws", "skill": "web_search", "input": {"query": "AWS status"},
                "metadata": {}, "state": "running", "result": None},
        "gcp": {"id": "gcp", "skill": "web_search", "input": {"query": "GCP status"},
                "metadata": {}, "state": "succeeded", "result": {"hits": []}},
    }
    reply = Replies(
        {"add": [], "cancel": ["aws"], "finish": False},
        {"add": [], "cancel": [], "finish": False,
         "reason": "wait for the independent AWS outcome"},
    )
    planner = GeneralAgentPlanner(reply, default_registry(), goal="Compare status pages",
                                  review_terminal=False)
    patch = await planner.plan(snapshot(nodes), Event(6, "task_succeeded", "gcp", {"hits": []}))
    assert not patch.cancel and not patch.finish
    assert planner.history[0]["accepted"] is False


@pytest.mark.asyncio
async def test_reproposing_identical_active_work_is_normalized_to_wait():
    nodes = {"research": {"id": "research", "skill": "researcher",
                          "input": {"query": "current evidence", "max_results": 3},
                          "metadata": {}, "state": "running", "result": None}}
    reply = Replies({"add": [{"id": "research_retry", "capability": "researcher",
                              "arguments": {"query": "current evidence", "max_results": 3},
                              "depends_on": []}], "cancel": [], "finish": False,
                     "reason": "retry research"})
    planner = GeneralAgentPlanner(reply, default_registry(), goal="Research a current fact", review_terminal=False)
    patch = await planner.plan(snapshot(nodes), Event(3, "task_succeeded", "other", {}))
    assert not patch.add


@pytest.mark.asyncio
async def test_partial_frontier_outcome_can_earn_one_bounded_follow_up():
    nodes = {
        "listing": {"id": "listing", "skill": "researcher", "input": {}, "metadata": {},
                    "state": "succeeded", "result": {"text": "candidate"}},
        "reviews": {"id": "reviews", "skill": "researcher", "input": {}, "metadata": {},
                    "state": "running", "result": None},
    }
    reply = Replies({"add": [{"id": "warranty", "capability": "researcher",
                              "arguments": {"query": "candidate warranty"}, "depends_on": ["listing"]}],
                     "cancel": [], "finish": False, "reason": "follow partial evidence"})
    planner = GeneralAgentPlanner(reply, default_registry(), goal="Compare a product",
                                  review_terminal=False)
    patch = await planner.plan(snapshot(nodes), Event(4, "task_succeeded", "listing", {"text": "candidate"}))
    assert [task.id for task in patch.add] == ["warranty"]
    assert patch.connect == (("listing", "warranty"),)
    assert len(patch.add) <= planner.max_new_tasks


@pytest.mark.asyncio
async def test_unknown_capability_is_rejected_and_repaired():
    reply = Replies(
        {"add": [{"id": "shell", "capability": "run_shell", "arguments": {"command": "rm -rf /"},
                  "depends_on": []}], "cancel": [], "finish": False, "reason": "try shell"},
        {"add": [{"id": "answer", "capability": "answer_with_evidence",
                  "arguments": {"query": "Explain that shell access is unavailable."}, "depends_on": []}],
         "cancel": [], "finish": False, "reason": "answer within available authority"},
    )
    planner = GeneralAgentPlanner(reply, default_registry(), goal="Delete the machine.", review_terminal=False)
    patch = await planner.plan(snapshot(), Event(1, "run_started", None, {}))
    assert [task.skill for task in patch.add] == ["answer_with_evidence"]
    assert planner.history[0]["accepted"] is False


@pytest.mark.asyncio
async def test_terminal_answer_is_blocked_when_generic_evidence_review_finds_missing_coverage():
    reply = Replies(
        {"add": [{"id": "answer", "capability": "answer_with_evidence",
                  "arguments": {"query": "recommend a current product"}, "depends_on": []}],
         "cancel": [], "finish": False, "reason": "answer now"},
        {"ready": False, "missing": ["current price", "independent review", "warranty"],
         "reason": "purchase constraints lack evidence"},
        {"add": [{"id": "research", "capability": "researcher",
                  "arguments": {"query": "current product price independent review warranty"},
                  "depends_on": []}], "cancel": [], "finish": False,
         "reason": "gather the missing evidence"},
    )
    planner = GeneralAgentPlanner(reply, default_registry(), goal="Recommend a current product with warranty")
    patch = await planner.plan(snapshot(), Event(1, "run_started", None, {}))
    assert [task.skill for task in patch.add] == ["researcher"]
    review = next(item for item in planner.history if item.get("kind") == "evidence_review")
    assert review["ready"] is False


@pytest.mark.asyncio
async def test_side_effect_requires_explicit_run_authority():
    reply = Replies(
        {"add": [{"id": "write", "capability": "write_file",
                  "arguments": {"path": "out.txt", "content": "x"}}]},
        {"add": [{"id": "answer", "capability": "answer_with_evidence",
                  "arguments": {"query": "Explain that write authority was not granted."}}]},
    )
    planner = GeneralAgentPlanner(reply, default_registry(), goal="Describe a possible file",
                                  review_terminal=False)
    patch = await planner.plan(snapshot(), Event(1, "run_started", None, {}))
    assert [task.skill for task in patch.add] == ["answer_with_evidence"]
    assert "lacks explicit run authority" in planner.history[0]["error"]


@pytest.mark.asyncio
async def test_capability_keyed_provider_shorthand_is_normalized_generically():
    reply = Replies({"answer_with_evidence": {"query": "Return the completed job receipt."}})
    planner = GeneralAgentPlanner(reply, default_registry(), goal="Return the receipt.",
                                  review_terminal=False)
    patch = await planner.plan(snapshot(), Event(1, "run_started", None, {}))
    assert [(task.skill, task.input) for task in patch.add] == [
        ("answer_with_evidence", {"query": "Return the completed job receipt."})
    ]


def test_runtime_contains_no_prompt_router_or_benchmark_case_logic():
    source = (Path(__file__).parents[1] / "sourcecode" / "runtime.py").read_text()
    assert "_work_intent" not in source
    assert "DeterministicPlanner" not in source
    assert "family-friendly things to do in Tokyo" not in source
    assert "populations? of" not in source
