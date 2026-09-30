"""The coding surface: a workspace the agent may change, and the tools to change it.

Every session so far let the agent *choose* code that humans wrote. This one lets
it write code. That is a different risk, and the whole module is shaped by it.

Four ideas carry the design:

**Read before you edit.** An edit to a file this run has not read is refused. Not
discouraged in a prompt: refused, in code. A model editing from memory is the
single most reliable way to destroy work nobody asked it to touch.

**Anchor, do not diff.** An edit names an exact string to replace. Unified diffs
need correct line numbers, and models are poor at line numbers, so a diff-based
agent spends its iterations fighting the patch format instead of the bug. An
anchor needs no arithmetic. It does need to be unique, and that requirement does
real work: to make it unique the model must include enough surrounding code to
prove it knows where it is.

**Never touch the judge.** The test suite is the only free, deterministic judge
this course has ever had. It stays free exactly as long as the agent cannot edit
it. A change that touches a test path is refused and recorded.

**Nothing runs unbounded.** Commands come from an allowlist, take no shell, run
only inside the workspace, and die on a timeout.
"""

from .edit import EditError, EditLedger, apply_edit
from .exec import CommandError, CommandResult, run_command
from .guard import GuardError, guard_path
from .search import glob_files, grep_code
from .workspace import Workspace, WorkspaceError

__all__ = [
    "CommandError", "CommandResult", "EditError", "EditLedger", "GuardError",
    "Workspace", "WorkspaceError", "apply_edit", "glob_files", "grep_code",
    "guard_path", "run_command",
]
