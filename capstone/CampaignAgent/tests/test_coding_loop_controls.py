"""The three controls that stop a coding loop eating itself.

Each one exists because of an observed failure, not a hypothetical:
a run that spent ten edits and four identical test failures fighting its own
test harness, never once touching the page it was supposed to build.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from sourcecode.capabilities import default_registry
from sourcecode.planner import GeneralAgentPlanner


class _Snapshot:
    """Just enough GraphSnapshot for the planner's stuck-check."""
    def __init__(self, nodes): self.nodes, self.edges = nodes, []


def _verify_node(command: str, exit_code: int) -> dict:
    return {"skill": "run_command", "state": "succeeded",
            "input": {"command": command}, "result": {"exit_code": exit_code}}


def _planner(**kwargs) -> GeneralAgentPlanner:
    async def never(p, s): raise AssertionError("no model call expected")
    return GeneralAgentPlanner(never, default_registry(), goal="x", **kwargs)


# ------------------------------------------------------- the repeat ceiling

def test_a_command_failing_the_same_way_repeatedly_stops_the_run() -> None:
    """The node limit misses this: a command returning 1 has *succeeded* at running."""
    planner = _planner(max_repeat_failures=4)
    graph = _Snapshot({f"v{i}": _verify_node("node check.js", 1) for i in range(4)})
    stuck = planner._stuck_verification(graph)          # noqa: SLF001
    assert stuck == ("node check.js", 4)


def test_three_failures_are_still_iteration_not_thrashing() -> None:
    planner = _planner(max_repeat_failures=4)
    graph = _Snapshot({f"v{i}": _verify_node("node check.js", 1) for i in range(3)})
    assert planner._stuck_verification(graph) is None   # noqa: SLF001


def test_a_pass_forgives_everything_before_it() -> None:
    """Converging is the point. Earlier failures are how you got there."""
    planner = _planner(max_repeat_failures=2)
    nodes = {f"v{i}": _verify_node("pytest -q", 1) for i in range(5)}
    nodes["v_ok"] = _verify_node("pytest -q", 0)
    assert planner._stuck_verification(_Snapshot(nodes)) is None   # noqa: SLF001


def test_different_commands_are_tallied_separately() -> None:
    planner = _planner(max_repeat_failures=3)
    nodes = {"a1": _verify_node("pytest -q", 1), "a2": _verify_node("pytest -q", 1),
             "b1": _verify_node("node check.js", 1), "b2": _verify_node("node check.js", 1)}
    assert planner._stuck_verification(_Snapshot(nodes)) is None   # noqa: SLF001


def test_the_ceiling_can_be_switched_off() -> None:
    planner = _planner(max_repeat_failures=0)
    graph = _Snapshot({f"v{i}": _verify_node("pytest", 1) for i in range(50)})
    assert planner._stuck_verification(graph) is None  # noqa: SLF001


# --------------------------------------------------------- the validator

def test_the_validator_is_declared_and_cannot_be_confused_with_building() -> None:
    registry = default_registry()
    assert "validate_work" in registry.family("verify")
    # It must be rerunnable: validating again after a fix is the whole point.
    assert "validate_work" in registry.family("rerunnable")


def test_the_validator_brief_is_hostile_and_forbids_editing() -> None:
    from sourcecode.coding.validate import VALIDATOR_SYSTEM, validator_goal
    assert "may NOT edit" in VALIDATOR_SYSTEM
    assert "find out where that belief is wrong" in VALIDATOR_SYSTEM
    # It must be told that a page can be present and still invisible.
    assert "opacity 0" in VALIDATOR_SYSTEM
    # The brief carries the requirement and the files, and no build history.
    goal = validator_goal("build a page", ["index.html"])
    assert "index.html" in goal and "build a page" in goal


def test_a_validator_that_ran_nothing_is_not_a_pass() -> None:
    """Saying 'looks fine' without executing anything is the failure that matters."""
    from sourcecode.coding.validate import summarise
    blocked = summarise({"passed": True, "summary": "seems ok", "findings": [
        {"what": "maybe broken", "severity": "blocker", "reproduced": False}]})
    assert blocked["passed"] is False          # a blocker overrides a claimed pass
    assert blocked["reproduced_any"] is False


def test_a_clean_validation_passes() -> None:
    from sourcecode.coding.validate import summarise
    assert summarise({"passed": True, "findings": [], "summary": "ran it, works"})["passed"]


# ------------------------------------------------------ the supplied harness

def _webcheck() -> Path:
    return Path(__file__).resolve().parents[1] / "sourcecode" / "coding" / "assets" / "webcheck.js"


def test_the_web_harness_ships_with_the_package() -> None:
    """The agent should not have to invent a browser test before it can check itself."""
    source = _webcheck().read_text()
    assert "opacity" in source            # visible, not merely present
    assert "SecurityError" in source      # the file:// origin case
    assert "no javascript" in source      # the JS-disabled case
    assert "process.exit(1)" in source    # it must be able to fail


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_the_harness_calls_a_blank_page_blank(tmp_path: Path) -> None:
    """The exact failure that fooled three hand-written checks."""
    page = tmp_path / "blank.html"
    page.write_text(
        "<!doctype html><style>.hide{opacity:0}</style>"
        "<body><div class='hide'>" + ("content " * 80) + "</div></body>")
    result = subprocess.run(["node", str(_webcheck()), str(page)],
                            capture_output=True, text=True, cwd=_webcheck().parent, timeout=90)
    if "needs jsdom" in result.stderr:
        pytest.skip("jsdom not installed next to webcheck.js")
    assert result.returncode == 1
    assert "effectively blank" in result.stderr
