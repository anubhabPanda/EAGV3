"""The coding surface, as ten plain functions.

Each one is a thin delegate onto ``sourcecode.coding``: the rules live there, in
guard.py, edit.py and exec.py, where they are tested directly. What lives here
is only the mapping from a capability's arguments to that call.

That thinness is the point. If a refusal needs changing, it changes in one place
in coding/, not in a closure buried a thousand lines inside a run.
"""
from __future__ import annotations

from typing import Any

from sourcecode.coding import glob_files, grep_code, run_command
from sourcecode.coding.edit import apply_edit, copy_within_workspace, read_code
from sourcecode.coding.edit import create_file as coding_create_file
from sourcecode.core.live_graph import TaskSpec

from .context import RunContext

__all__ = [
    "read_code_worker", "edit_code_worker", "create_file_worker",
    "copy_code_file_worker", "glob_files_worker", "grep_code_worker",
    "run_command_worker", "git_diff_worker", "git_reset_worker",
]


async def read_code_worker(ctx: RunContext, task: TaskSpec) -> dict[str, Any]:
    return read_code(ctx.workspace(), ctx.ledger, task.input["path"],
                     offset=int(task.input.get("offset", 1)),
                     limit=int(task.input.get("limit", 200)))


async def edit_code_worker(ctx: RunContext, task: TaskSpec) -> dict[str, Any]:
    return apply_edit(ctx.workspace(), ctx.ledger, task.input["path"],
                      old_string=task.input["old_string"],
                      new_string=task.input["new_string"],
                      replace_all=bool(task.input.get("replace_all", False)))


async def create_file_worker(ctx: RunContext, task: TaskSpec) -> dict[str, Any]:
    return coding_create_file(ctx.workspace(), ctx.ledger, task.input["path"],
                              content=task.input["content"],
                              overwrite=bool(task.input.get("overwrite", False)))


async def copy_code_file_worker(ctx: RunContext, task: TaskSpec) -> dict[str, Any]:
    return copy_within_workspace(ctx.workspace(), ctx.ledger,
                                 task.input["source"], task.input["destination"],
                                 overwrite=bool(task.input.get("overwrite", False)))


async def glob_files_worker(ctx: RunContext, task: TaskSpec) -> dict[str, Any]:
    return glob_files(ctx.workspace(), task.input["pattern"])


async def grep_code_worker(ctx: RunContext, task: TaskSpec) -> dict[str, Any]:
    return grep_code(ctx.workspace(), task.input["pattern"],
                     path_glob=task.input.get("path_glob", "*"),
                     ignore_case=bool(task.input.get("ignore_case", False)))


async def run_command_worker(ctx: RunContext, task: TaskSpec) -> dict[str, Any]:
    return run_command(ctx.workspace(), task.input["command"],
                       timeout=int(task.input.get("timeout", 120)))


async def git_diff_worker(ctx: RunContext, task: TaskSpec) -> dict[str, Any]:  # noqa: ARG001
    """Uses the workspace's own diff, not the command runner.

    Shelling out to `git diff` would route this through the allowlist and the
    metacharacter check for no benefit: the workspace already knows how to
    describe its own changes, and it is not subject to a timeout or an output cap.
    """
    workspace = ctx.workspace()
    return {"diff": workspace.diff() or "(no changes)",
            "files": workspace.changed_files()}


async def git_reset_worker(ctx: RunContext, task: TaskSpec) -> dict[str, Any]:  # noqa: ARG001
    workspace = ctx.workspace()
    changed = workspace.changed_files()
    workspace.reset()
    return {"reset": True, "discarded": changed}
