"""Build a declarative A2UI surface from a graph snapshot.

The builder never emits markup. It emits a flat adjacency list of components
(A2UI style: an array linked by id, one ``root``) plus a data model the
components bind into. Structure and data travel apart, so no value the surface
shows is ever code.

Two shapes are built here:
  - ``build_run_surface``   a live view of a run: nodes as cards, the answer,
    and an honest Notice when a node failed or evidence is missing.
  - ``build_approval_surface`` an ApprovalCard bound to a pending action's
    exact parameters (see hitl.py for why the binding is the safety).

Both return ``{"root", "components", "dataModel"}``. The result is validated by
validator.py before it is served, exactly as an untrusted agent's surface would
be.
"""

from __future__ import annotations

from typing import Any

_TONE_FOR_STATE = {
    "succeeded": "good",
    "running": "neutral",
    "pending": "neutral",
    "failed": "bad",
    "cancelled": "warn",
    "waiting": "warn",
}


def build_run_surface(snapshot: dict) -> dict:
    """A live surface for a run snapshot ``{run_id, finished, nodes, edges}``."""
    nodes: dict[str, dict] = snapshot["nodes"]
    components: list[dict] = []
    data_model: dict[str, Any] = {"title": f"Run {snapshot['run_id']}", "rows": [], "answer": ""}

    children: list[str] = ["h_title"]
    components.append({"id": "h_title", "type": "Text", "variant": "heading", "text": {"$bind": "/title"}})

    # One card row per node: a name Text + a StatTile that carries the node's
    # state and colours it by tone (StatTile replaces the old Badge; it keeps
    # the tone the Badge carried and is a real catalog component).
    for i, (nid, node) in enumerate(sorted(nodes.items())):
        state = node["state"]
        row_id = f"row_{i}"
        name_id, state_id = f"name_{i}", f"state_{i}"
        data_model[f"node_{i}_name"] = f"{nid}  ·  {node['skill']}"
        data_model[f"node_{i}_state"] = state
        components.append(
            {"id": row_id, "type": "Row", "align": "center", "justify": "spaceBetween",
             "children": [name_id, state_id]}
        )
        components.append({"id": name_id, "type": "Text", "variant": "body", "text": {"$bind": f"/node_{i}_name"}})
        components.append(
            {"id": state_id, "type": "StatTile", "label": "state", "value": {"$bind": f"/node_{i}_state"},
             "tone": _TONE_FOR_STATE.get(state, "neutral")}
        )
        children.append(row_id)

    # The answer, if a node named 'answer' or 'answer_worker' succeeded.
    answer_text = _find_answer(nodes)
    if answer_text is not None:
        data_model["answer"] = answer_text
        components.append({"id": "answer", "type": "Text", "text": {"$bind": "/answer"}})
        children.append("answer")

    # Honest failure: any failed node yields a Notice instead of pretending.
    failed = [nid for nid, n in nodes.items() if n["state"] == "failed"]
    if failed:
        data_model["notice"] = f"{len(failed)} task(s) failed: {', '.join(sorted(failed))}. No result was invented."
        components.append({"id": "notice", "type": "Notice", "text": {"$bind": "/notice"}, "tone": "bad"})
        children.append("notice")

    components.insert(0, {"id": "root", "type": "Column", "children": children})
    return {"root": "root", "components": components, "dataModel": data_model}


def build_approval_surface(run_id: str, node_id: str, summary: str, params: dict) -> dict:
    """An ApprovalCard bound to the exact params of a waiting action."""
    data_model = {"summary": summary, "params": params}
    components = [
        {"id": "root", "type": "Column", "children": ["card"]},
        {
            "id": "card",
            "type": "ApprovalCard",
            "summary": {"$bind": "/summary"},
            "params": {"$bind": "/params"},
            # The confirm action carries the SAME bound params the card shows.
            # hitl.py re-checks these against the parked node on resume.
            "confirm": {"action": "approve", "args": {"$bind": "/params"}},
            "reject": {"action": "reject", "args": {"run_id": run_id, "node_id": node_id}},
        },
    ]
    return {"root": "root", "components": components, "dataModel": data_model}


def _find_answer(nodes: dict[str, dict]) -> str | None:
    for nid, node in nodes.items():
        if node["state"] == "succeeded" and ("answer" in nid or node["skill"] in ("answer", "answerer")):
            result = node.get("result") or {}
            if isinstance(result, dict):
                for key in ("text", "answer", "output"):
                    if key in result and isinstance(result[key], str):
                        return result[key]
    return None
