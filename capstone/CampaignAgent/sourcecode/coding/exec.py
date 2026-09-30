"""Running the judge, and nothing else.

This is the most dangerous capability in the course. Every session before this
one let the agent choose among tools that humans wrote. Here the agent writes the
thing that then executes, which is the situation Session 12 built containers for
and which nothing since has actually needed.

Four bounds, all enforced here rather than requested in a prompt:

**No shell.** The command is a list of arguments. There is no shell to interpret
`;`, `&&`, backticks or `rm -rf ~`, because no shell is ever involved.

**An allowlist.** `argv[0]` must be a command we chose. A model that decides the
fix requires `curl | sh` gets a refusal, not a subprocess.

**Inside the workspace.** The working directory is the workspace and cannot be
changed by the caller.

**Bounded.** A wall-clock timeout kills it, and the output is capped, because a
test suite that prints a million lines will otherwise eat the context that was
supposed to hold the fix.

`S17_EXEC_CONTAINER=1` runs the same command inside a container instead, which is
what a real deployment does. The allowlist is the floor beneath that, not a
replacement for it.
"""
from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass

from .workspace import Workspace

DEFAULT_ALLOWLIST = ("pytest", "python", "python3", "uv", "ruff", "mypy", "git", "node", "npm")
MAX_OUTPUT_CHARS = 20_000
DEFAULT_TIMEOUT = 120
MAX_TIMEOUT = 600

# Even inside an allowlisted command, these turn a test run into something else.
FORBIDDEN_ARGS = ("--user", "--system", "-c")

# Characters that only mean anything to a shell. We never invoke one, so their
# presence means the caller believed it had a shell. Refuse loudly rather than
# passing them through as a harmless-looking argument.
SHELL_METACHARACTERS = (";", "&&", "||", "|", "`", "$(", ">", "<", "\n")

# `git` can execute arbitrary programs through several flags and config keys, so
# only plainly read-only or workspace-local subcommands are permitted.
GIT_SUBCOMMANDS = ("status", "diff", "log", "show", "add", "commit", "checkout",
                   "restore", "branch", "rev-parse", "stash", "clean")


class CommandError(ValueError):
    """The command was refused before anything ran."""


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    duration_seconds: float

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    def as_dict(self) -> dict:
        return {"command": " ".join(self.command), "exit_code": self.exit_code,
                "ok": self.ok, "timed_out": self.timed_out,
                "duration_seconds": round(self.duration_seconds, 3),
                "stdout": self.stdout, "stderr": self.stderr}


def allowlist() -> tuple[str, ...]:
    configured = os.getenv("S17_ALLOWED_COMMANDS", "").strip()
    if configured:
        return tuple(c.strip() for c in configured.split(",") if c.strip())
    return DEFAULT_ALLOWLIST


def _check(argv: list[str]) -> None:
    if not argv:
        raise CommandError("no command given")
    for token in argv:
        for meta in SHELL_METACHARACTERS:
            if meta in token:
                raise CommandError(
                    f"{meta!r} has no meaning here: commands run without a shell. "
                    "Run one program per call."
                )
    program = os.path.basename(argv[0])
    if program not in allowlist():
        raise CommandError(
            f"{program!r} is not an allowed command. Allowed: {', '.join(allowlist())}. "
            "The agent runs the tests; it does not get a shell."
        )
    for argument in argv[1:]:
        # `python -c "..."` is a shell by another name.
        if program.startswith("python") and argument == "-c":
            raise CommandError("python -c is refused: it is an unbounded shell")
        if argument in FORBIDDEN_ARGS and program in {"pip", "uv"}:
            raise CommandError(f"{argument!r} is refused for {program}")
    if program == "git":
        # `git -c ...`, `--upload-pack` and friends can run arbitrary programs.
        subcommand = next((a for a in argv[1:] if not a.startswith("-")), "")
        if subcommand not in GIT_SUBCOMMANDS:
            raise CommandError(
                f"git {subcommand or '(none)'} is refused. Allowed: "
                f"{', '.join(GIT_SUBCOMMANDS)}."
            )
        if any(a.startswith("-c") or "upload-pack" in a or "receive-pack" in a for a in argv[1:]):
            raise CommandError("git config and pack overrides can execute programs; refused")


def run_command(workspace: Workspace, command: str | list[str], *,
                timeout: int = DEFAULT_TIMEOUT) -> CommandResult:
    """Run one allowlisted command inside the workspace, bounded."""
    argv = shlex.split(command) if isinstance(command, str) else list(command)
    _check(argv)
    timeout = max(1, min(int(timeout), MAX_TIMEOUT))

    if os.getenv("S17_EXEC_CONTAINER", "").strip() == "1":
        image = os.getenv("S17_EXEC_IMAGE", "python:3.11-slim")
        argv = ["docker", "run", "--rm", "--network=none",
                "--memory=1g", "--cpus=1", "--pids-limit=256",
                "-v", f"{workspace.root}:/workspace", "-w", "/workspace",
                image, *argv]

    import time
    started = time.monotonic()
    try:
        completed = subprocess.run(
            argv, cwd=workspace.root, capture_output=True, text=True,
            timeout=timeout, shell=False,            # never a shell
            env={"PATH": os.environ.get("PATH", ""), "HOME": str(workspace.root),
                 "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"},
        )
        return CommandResult(
            argv, completed.returncode,
            completed.stdout[-MAX_OUTPUT_CHARS:], completed.stderr[-MAX_OUTPUT_CHARS:],
            False, time.monotonic() - started,
        )
    except subprocess.TimeoutExpired as expired:
        return CommandResult(
            argv, 124,
            (expired.stdout or b"").decode(errors="replace")[-MAX_OUTPUT_CHARS:]
            if isinstance(expired.stdout, bytes) else (expired.stdout or "")[-MAX_OUTPUT_CHARS:],
            f"timed out after {timeout}s", True, time.monotonic() - started,
        )
    except FileNotFoundError as missing:
        raise CommandError(f"command not found: {argv[0]}") from missing
