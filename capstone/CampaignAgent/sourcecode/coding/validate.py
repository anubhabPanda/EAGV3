"""A validator that is a different agent, with a different job and no hands.

The builder has just written fifty kilobytes and believes it works. Asking it to
check its own output gets you the same blind spots that produced the bug: it
tests what it was thinking about, in the environment it was imagining.

So validation is a **separate run**, and three things make it separate:

**A fresh context.** The validator never sees the build conversation. It sees the
artifact and the requirement, nothing else, so it cannot inherit the builder's
assumptions about what "obviously works".

**A hostile brief.** It is asked to find what is broken, not to confirm that
things are fine. Session 15 called this an adversarial verifier; the difference
in what it finds is not subtle.

**No hands.** The validator may read, search and run commands. It may not edit.
A thing that can fix what it grades will eventually grade what it can fix, which
is the same rule that keeps the test suite out of the builder's reach.

It returns findings. The builder's graph decides what to do about them, which is
how a failed validation earns the next attempt rather than ending the run.
"""
from __future__ import annotations

from typing import Any

VALIDATOR_SYSTEM = (
    "You are a validation agent. Something has been built and somebody believes "
    "it works. Your job is to find out where that belief is wrong.\n\n"
    "You may read files, search them, and run commands. You may NOT edit "
    "anything: you report, you do not repair.\n\n"
    "Do not accept that code exists as evidence that code runs. Execute it. "
    "Where the artifact is a web page, load it in a headless DOM and check what "
    "a person would actually see, not merely what is present in the document: "
    "an element left at opacity 0 by an entrance animation is not visible. Test "
    "the environments a real user will have and the author did not try, "
    "including a file:// origin where storage APIs throw, and a browser where "
    "JavaScript fails entirely.\n\n"
    "Write whatever test scripts you need in order to prove a defect. A defect "
    "you have not reproduced is a guess, and you must label it as one.\n\n"
    "Return JSON only:\n"
    '{"passed": bool, "findings": [{"what": str, "evidence": str, '
    '"reproduced": bool, "severity": "blocker"|"major"|"minor"}], "summary": str}\n'
    "An empty findings list means you executed the artifact and it genuinely "
    "worked. Saying so without having run anything is the one failure that "
    "matters here."
)


def validator_goal(requirement: str, paths: list[str] | None = None) -> str:
    """The whole brief the validator gets. Deliberately no build history."""
    targets = ("\n\nFiles to examine: " + ", ".join(paths)) if paths else ""
    return (
        "Validate that this requirement is genuinely met by what is in the "
        f"workspace.\n\nRequirement:\n{requirement}{targets}\n\n"
        "Run it. Report what is broken."
    )


def summarise(result: dict[str, Any]) -> dict[str, Any]:
    """Flatten a validator run into something a planner can act on."""
    findings = result.get("findings") or []
    blockers = [f for f in findings if f.get("severity") == "blocker"]
    return {
        "passed": bool(result.get("passed")) and not blockers,
        "blockers": len(blockers),
        "findings": findings,
        "summary": result.get("summary", ""),
        # The planner reads this: a validator that found nothing AND ran nothing
        # is not a pass, it is an untested artifact.
        "reproduced_any": any(f.get("reproduced") for f in findings),
    }
