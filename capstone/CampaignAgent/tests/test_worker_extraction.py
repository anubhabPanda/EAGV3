"""The extracted workers must behave exactly like the closures they replaced.

Moving forty-eight closures out of a thousand-line function is mechanical, which
is precisely why it is dangerous: a worker that is subtly rewritten during the
move still passes every test that only checks the capability exists. During this
extraction `git_diff` was rewritten to shell out to `git diff` instead of using
the workspace's own diff, and the whole suite stayed green.
"""
from __future__ import annotations

import inspect

import pytest

from sourcecode.workers import RunContext
from sourcecode.workers import coding as workers


def test_git_workers_use_the_workspace_not_the_command_runner() -> None:
    """Routing these through run_command would subject them to the allowlist,
    the metacharacter check and an output cap, for no benefit."""
    for fn in (workers.git_diff_worker, workers.git_reset_worker):
        src = inspect.getsource(fn)
        assert "ctx.workspace()" in src
        assert "run_command(" not in src, f"{fn.__name__} must not shell out"


def test_every_worker_takes_a_context_and_a_task() -> None:
    for name in workers.__all__:
        fn = getattr(workers, name)
        params = list(inspect.signature(fn).parameters)
        assert params == ["ctx", "task"], f"{name} has {params}"
        assert inspect.iscoroutinefunction(fn), f"{name} must be async"


def test_the_context_cannot_be_mutated_by_a_worker() -> None:
    """A worker that could swap the registry could change what the run may do."""
    ctx = RunContext(run_id="r", runtime=None, llm=None, scope=None,
                     registry=None, ledger=None)
    with pytest.raises(Exception):
        ctx.run_id = "other"  # type: ignore[misc]


def test_the_context_carries_only_what_was_measured() -> None:
    """Eight fields, and the eighth is a correction.

    The first AST pass reported seven, because it filtered `prompt` out as a
    local name. It is not: the composer titles a surface with the run's goal,
    and it read that straight from the enclosing scope. The measurement was
    wrong, not the code.

    This assertion is exact on purpose. If it grows again, something is being
    dragged into the context instead of being passed to the one worker that
    needs it, which is how forty-eight closures happened the first time.
    """
    import dataclasses

    fields = {f.name for f in dataclasses.fields(RunContext)}
    assert fields == {"run_id", "runtime", "llm", "scope", "registry",
                      "ledger", "transport", "goal"}


def test_the_coding_workers_are_thin() -> None:
    """The rules live in coding/. A worker that grows logic has stolen it."""
    for name in workers.__all__:
        body = [l for l in inspect.getsource(getattr(workers, name)).splitlines()
                if l.strip() and not l.strip().startswith(("#", '"""', "'''"))]
        assert len(body) <= 12, f"{name} is {len(body)} lines; the rule belongs in coding/"
