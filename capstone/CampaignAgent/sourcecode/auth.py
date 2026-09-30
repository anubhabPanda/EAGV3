"""Bearer-token gates for the S17 control plane.

Every gate here **fails closed**. If the token is not configured the endpoint
returns 503 and refuses to serve, rather than quietly serving everybody.

That choice is the whole point. An autonomous agent's control plane is a
different kind of surface from a chat endpoint: a subscription carries
`allowed_side_effects` and a `budget`, so whoever can write one can decide what
the agent is allowed to do and how much it may spend. An unauthenticated write
path there is not a missing feature, it is a way to hand an anonymous caller
the authority the whole design rests on.

`if expected and not compare_digest(...)` is the shape to avoid: it reads like a
check and behaves like an open door whenever the variable is unset, which is
exactly the state a fresh checkout is in.
"""
from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException

CONTROL_TOKEN_ENV = "S17_CONTROL_TOKEN"
COMPLETION_TOKEN_ENV = "S17_COMPLETION_TOKEN"


def _require(env_name: str, authorization: str | None, *, surface: str) -> None:
    expected = os.getenv(env_name, "").strip()
    if not expected:
        raise HTTPException(
            503,
            f"{env_name} is not configured; the {surface} refuses to serve without it",
        )
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(401, f"invalid {surface} token")


async def require_control(authorization: str | None = Header(default=None)) -> None:
    """Guard anything that creates authority, starts work, or spends money."""
    _require(CONTROL_TOKEN_ENV, authorization, surface="control plane")


async def require_completion(authorization: str | None = Header(default=None)) -> None:
    """Guard the callback that resumes a parked node from outside this process.

    A separate token from the control plane: the holder is a remote job service,
    which should be able to complete work it was given without also being able
    to write subscriptions.
    """
    _require(COMPLETION_TOKEN_ENV, authorization, surface="completion callback")
