"""The optimizer is in the run path, or it is a library pretending to be a feature.

An earlier draft of Session 17 said "something sits in front of the planner and
restates the request". Nothing did: QueryOptimizer existed, had fourteen passing
tests, and was never called. These tests hold the wiring itself.
"""
from __future__ import annotations

import inspect

from sourcecode import runtime as rt


def _run_source() -> str:
    return inspect.getsource(rt.AgentRuntime.run)


def test_the_optimizer_is_actually_called_in_the_run_path() -> None:
    src = _run_source()
    assert "QueryOptimizer" in src, "the optimizer is not in run(); §13 would be false"
    assert "restated_goal = optimized.planning_goal()" in src


def test_the_planner_plans_against_the_restated_goal() -> None:
    src = _run_source()
    assert "goal=restated_goal" in src, "the rewrite must reach the planner to mean anything"


def test_it_is_off_unless_switched_on() -> None:
    """One extra model call before any work starts is not a default."""
    src = _run_source()
    assert 'os.getenv("S17_QUERY_OPTIMIZER", "0")' in src


def test_a_resumed_run_is_not_rewritten_again() -> None:
    """Resume reloads the goal from the journal. Rewriting it twice would mean a
    run silently changing its own objective between checkpoints."""
    src = _run_source()
    i = src.index("S17_QUERY_OPTIMIZER")
    assert "not resume" in src[i:i + 200]


def test_the_original_prompt_survives_into_the_goal() -> None:
    """planning_goal() carries the original verbatim, so the journal shows both."""
    from sourcecode.reasoning import OptimizedQuery

    q = OptimizedQuery(original="fix login", query="Find and fix the login failure.",
                       constraints=("do not change the API",), rewritten=True)
    goal = q.planning_goal()
    assert "fix login" in goal and "do not change the API" in goal


def test_a_failed_rewrite_leaves_the_prompt_untouched() -> None:
    from sourcecode.reasoning import OptimizedQuery

    q = OptimizedQuery(original="fix login", query="fix login", rewritten=False,
                       rejected_because="optimizer error: provider down")
    assert q.planning_goal() == "fix login"
