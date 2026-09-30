"""Small pure helpers shared by the runtime and the workers.

They were module-level in runtime.py, which meant a worker that needed one had
to import the runtime, and the runtime imports the workers. Nothing here touches
state, so it belongs where both sides can reach it without a cycle.
"""
from __future__ import annotations

import json
import re
from typing import Any


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "item"

def _parse_json_object(text: str) -> dict[str, Any] | None:
    """Robustly parse a JSON object out of a model reply: strip ``` fences, then
    fall back to the outermost {...} span. Returns the dict or None. Shared by
    the content role (structured answer) and compose_surface (surface tree)."""
    if not isinstance(text, str):
        return None
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```[a-zA-Z]*\n?", "", candidate)
        candidate = re.sub(r"\n?```\s*$", "", candidate)
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(candidate[start:end + 1])
                return parsed if isinstance(parsed, dict) else None
            except Exception:
                return None
        return None

def _parse_json_array(text: str) -> list[Any] | None:
    """The array counterpart of ``_parse_json_object``."""
    candidate = (text or "").strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.I)
        candidate = re.sub(r"\s*```$", "", candidate)
    start, end = candidate.find("["), candidate.rfind("]")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(candidate[start:end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, list) else None

def _as_section(item: dict[str, Any]) -> dict[str, Any]:
    """Fold one arbitrary object into {heading, points, detail}."""
    used: set[str] = set()

    def first(tokens: tuple[str, ...]) -> Any:
        # Exact key wins; otherwise the first key containing the token. A model
        # asked for a heading writes "question_text" or "stem" as readily as
        # "heading", and an exact-match table silently drops the real content
        # into the leftovers. We watched exactly that: ten questions whose stems
        # ended up buried at the top of the solution text.
        for token in tokens:
            if token in item and item[token] not in (None, "", [], {}) and token not in used:
                used.add(token)
                return item[token]
        for token in tokens:
            for key, value in item.items():
                if key in used or value in (None, "", [], {}):
                    continue
                if token in key.lower().replace("-", "_"):
                    used.add(key)
                    return value
        return None

    # Heading first: it is computed last in the return statement otherwise, so
    # its key is still unclaimed when the leftovers are gathered and the stem
    # gets appended to the detail it was supposed to head.
    heading = first(_HEADING_KEYS)
    points = first(_POINTS_KEYS)
    if isinstance(points, (str, int, float)):
        points = [points]
    detail = first(_DETAIL_KEYS)
    # Anything the three slots did not claim is still information; keeping it
    # out of the detail would silently drop content the model chose to include.
    leftovers = [f"{k}: {v}" for k, v in item.items()
                 if k not in used and isinstance(v, (str, int, float)) and str(v).strip()]
    detail_text = "\n\n".join(part for part in [str(detail or "").strip(), *leftovers] if part)
    return {"heading": str(heading or "").strip(),
            "points": [str(p).strip() for p in (points or []) if str(p).strip()],
            "detail": detail_text}

_HEADING_KEYS = ("heading", "title", "name", "label", "stem", "question", "prompt", "text")

_POINTS_KEYS = ("points", "options", "choices", "bullets", "items", "steps")

_DETAIL_KEYS = ("detail", "solution", "answer", "explanation", "body", "description", "notes")
