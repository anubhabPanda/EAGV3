"""Bridge to llm_gatewayV9.

V9 is V8 plus two things: (1) `/v1/vision` — typed shim for single-image
vision calls that the Browser skill's Layer-3 driver hits; (2) per-agent
USD pricing on `/v1/cost/by_agent` so the ledger surfaces dollars in
addition to tokens. V8's `agent` tagging, `/v1/chat/batch`, and retry-
on-5xx carry forward unchanged.

The session-version mapping (V9 for Session 9) lets V8 stay frozen for
Session 8.

Auto-starts the gateway on port 8109 if it is not already up, then
re-exports the V9 `LLM` client and a module-level `embed()` helper.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
import os as _os

import httpx

GATEWAY_V9_DIR = Path(
    _os.environ.get("EAGV3_GATEWAY_V9_DIR")
    or r"D:\2026\EAG3\resources\llm_gatewayV9"
).resolve()
GATEWAY_URL = "http://localhost:8109"


def _is_up() -> bool:
    try:
        httpx.get(f"{GATEWAY_URL}/v1/routers", timeout=2.0)
        return True
    except Exception:
        return False


def ensure_gateway() -> None:
    """Start V9 if it is not already running. Idempotent."""
    if _is_up():
        return
    if not GATEWAY_V9_DIR.exists():
        raise RuntimeError(
            f"Gateway V9 directory not found at {GATEWAY_V9_DIR}. "
            "Build llm_gatewayV9 (Session 9 prerequisite) before running S9 code."
        )
    print(f"[gateway] launching llm_gatewayV9 from {GATEWAY_V9_DIR}")
    subprocess.Popen(
        ["uv", "run", "main.py"],
        cwd=str(GATEWAY_V9_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(45):
        time.sleep(1)
        if _is_up():
            print(f"[gateway] up on {GATEWAY_URL}")
            return
    raise RuntimeError(f"Gateway V9 failed to start within 45s. Check {GATEWAY_V9_DIR}")


# Load V9's client.py without polluting sys.path. The gateway dir has its
# own `schemas.py`, which would shadow ours if we put it on the path.
import importlib.util as _importlib_util

_LLM_CLASS = None  # cached LLM class after first load


def _load_llm_client_class():
    """Lazy-load the LLM client class from the gateway directory."""
    global _LLM_CLASS
    if _LLM_CLASS is not None:
        return _LLM_CLASS

    _client_path = GATEWAY_V9_DIR / "client.py"
    if not _client_path.exists():
        raise RuntimeError(
            f"Gateway V9 client unavailable. Expected client.py at {_client_path}. "
            "Build llm_gatewayV9 (Session 9 prerequisite) before running S9 code."
        )

    _spec = _importlib_util.spec_from_file_location("llm_gatewayV9_client", _client_path)
    _mod = _importlib_util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    _LLM_CLASS = _mod.LLM
    return _LLM_CLASS


class LLM:
    """Lazy-loading wrapper for the gateway LLM client.

    This class acts as a proxy that loads the actual LLM client from the
    gateway directory on first use, avoiding import-time failures when
    client.py doesn't exist yet.
    """
    def __new__(cls):
        # Return an instance of the actual LLM class from the gateway
        actual_llm_class = _load_llm_client_class()
        return actual_llm_class()


def embed(text: str, task_type: str = "retrieval_document") -> dict:
    """Compute an embedding for `text` via the gateway's embed endpoint.

    Returns the full response dict: `{embedding, dim, model, provider,
    latency_ms, ...}`. The chosen embedding model is fixed at the gateway
    level. Changing it invalidates every FAISS index built against the old
    vectors, so callers should treat the model as a project-level constant.
    """
    ensure_gateway()
    return LLM().embed(text, task_type=task_type)


__all__ = ["ensure_gateway", "LLM", "GATEWAY_URL", "GATEWAY_V9_DIR", "embed"]
