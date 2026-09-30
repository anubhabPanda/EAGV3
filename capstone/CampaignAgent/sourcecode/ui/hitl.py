"""Human-in-the-loop approval, bound to final parameters.

A high-impact action parks its node in S13's ``waiting`` state and records the
exact parameters it intends to run. The surface shows an ApprovalCard bound to
those parameters. When the user presses Approve, the client sends an
``approve`` action carrying args.

The safety is Session 12's sixth invariant: the approval is bound to the final
parameters. On resume we compare the args the client sent against the params
the node parked with. If a compromised client widened or altered them, the
resume is refused and the node stays waiting. A person who approved one action
cannot be made to authorise another.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PendingAction:
    run_id: str
    node_id: str
    summary: str
    params: dict


@dataclass(frozen=True)
class ResumeDecision:
    allowed: bool
    reason: str


def _canonical(value):
    """Order-independent canonical form for structural equality checks."""
    if isinstance(value, dict):
        return tuple(sorted((k, _canonical(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_canonical(v) for v in value)
    return value


def decide_resume(pending: PendingAction, action_name: str, args: dict) -> ResumeDecision:
    """Decide whether an approval action may resume the parked node."""
    if action_name == "reject":
        return ResumeDecision(True, "rejected by user")
    if action_name != "approve":
        return ResumeDecision(False, f"unexpected action {action_name!r} for approval")
    if _canonical(args) != _canonical(pending.params):
        return ResumeDecision(
            False,
            "approved args differ from the parked parameters; approval is bound to final params",
        )
    return ResumeDecision(True, "approved with matching parameters")
