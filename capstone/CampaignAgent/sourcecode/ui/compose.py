"""Composing an A2UI surface from what a run actually produced.

This was 287 lines inside ``AgentRuntime.run``, which is a quarter of that
function and the single largest reason it could not be read. It is a UI concern:
it imports the catalog and the validator, and everything it does is decide which
components to offer the model and which pointers exist to bind them to. It
belongs beside them.

The shape it enforces is the one the a2ui skill describes from the other side:
the model chooses structure, the harness owns the data model, and a pointer the
model invents resolves to nothing. Structure and data travel apart so that no
value a surface displays can ever be executed.
"""
from __future__ import annotations

import json
import re
from typing import Any

from sourcecode.core.live_graph import TaskSpec
from sourcecode.workers.context import RunContext

__all__ = ["compose_surface"]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(text).lower()).strip("_") or "item"


def _parse_json_object(text: str) -> dict[str, Any] | None:
    """Local copy: the composer must not import back into the runtime."""
    candidate = (text or "").strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.I)
        candidate = re.sub(r"\s*```$", "", candidate)
    start, end = candidate.find("{"), candidate.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(candidate[start:end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _extract_surface(text: str) -> dict[str, Any] | None:
    return _parse_json_object(text)

def _clean_key(text: str) -> str:
    return _slug(text)


async def compose_surface(ctx: RunContext, task: TaskSpec, *, surface_llm: Any) -> dict[str, Any]:
    """DOMAIN-AGNOSTIC surface composition. Build a GENERIC data model from
    this run's real upstream outcomes — one entry per succeeded non-compose
    node, plus a handful of generic fields any interface can bind to — then
    ask the model to compose an A2UI interface for the goal against that
    data model. Nothing here names a domain: the model chooses the title,
    layout and components from the actual data + the goal."""
    from sourcecode.ui.catalog import catalog_manifest
    from sourcecode.ui.validator import validate_surface

    snapshot = ctx.runtime.graph.snapshot(ctx.run_id)
    # Iterate succeeded non-compose nodes. If the planner chose to repair
    # weak evidence, both attempts remain visible; synthesis decides which
    # claims are supported instead of hiding history by naming convention.
    outcomes: list[dict[str, Any]] = []
    summary_parts: list[str] = []
    node_data: dict[str, Any] = {}
    content_structured: dict[str, Any] = {}  # the single-goal content role's structured answer
    # A synthesis node folds into the goal-level summary instead of
    # becoming one listed item. Membership is declared on the capability
    # (family "synthesis"), never inferred from what a node was named:
    # IDs are labels, not semantics.
    synthesis_skills = ctx.registry.family("synthesis")
    for node_id, node in sorted(snapshot.nodes.items()):
        if node["skill"] in ctx.registry.terminal_skills("ui") or node["state"] != "succeeded":
            continue
        result = node.get("result") or {}
        subject = (node.get("input") or {}).get("subject") or node_id
        text = (result.get("text") or result.get("answer") or "").strip()
        public_result = {key: value for key, value in result.items()
                         if key not in {"metered_calls", "budget_decisions", "raw", "pages"}}
        hits = result.get("hits") or []
        sources = [hit.get("url", "") for hit in hits if hit.get("url")]
        # A content node also carries a GENERIC STRUCTURED answer that
        # the rich components bind to (charts, cards, tables, choices).
        if node["skill"] in synthesis_skills:
            if isinstance(result.get("structured"), dict):
                content_structured = result["structured"]
            if text:
                summary_parts.append(text)
            continue
        detail = text or json.dumps(public_result, ensure_ascii=False, default=str)
        numeric_value = result.get("result") if isinstance(result.get("result"), (int, float)) else None
        outcome = {"key": _clean_key(subject), "label": subject,
                   "detail": detail[:2_000], "sources_count": len(sources),
                   "value": numeric_value}
        outcomes.append(outcome)
        node_data[outcome["key"]] = {"label": subject, "detail": detail[:2_000],
                                     "sources": sources, "result": public_result}

    summary = "\n\n".join(part for part in summary_parts if part)[:2000]

    # A GENERIC data model: the run goal, a synthesis summary, an items/
    # results array any list/table/tabs/chart can bind to, a numeric metric
    # series, a timeline of the run's own journal, and progress. No invented
    # domain fields — the real data is exposed generically.
    data_model: dict[str, Any] = {
        "title": ctx.goal,
        "goal": ctx.goal,
        "summary": summary or ctx.goal,
        "results": [{"label": item["label"], "detail": item["detail"]} for item in outcomes],
        "items": [{"label": item["label"]} for item in outcomes],
        "metrics": [{"label": item["label"], "value": item["value"]
                     if item["value"] is not None else item["sources_count"]} for item in outcomes],
        "spark": [float(item["value"] if item["value"] is not None else item["sources_count"])
                  for item in outcomes],
        "table_rows": [{"Item": item["label"], "Sources": item["sources_count"]} for item in outcomes],
        "item_count": len(outcomes),
        "source_count": sum(item["sources_count"] for item in outcomes),
        "evidence": node_data,
    }
    for index, item in enumerate(outcomes):
        data_model[f"item_{index}_label"] = item["label"]
        data_model[f"item_{index}_detail"] = item["detail"] or item["label"]
        if item["value"] is not None:
            data_model[f"item_{index}_value"] = item["value"]
        result = node_data[item["key"]]["result"]
        for field, value in result.items():
            if isinstance(value, (str, int, float, bool, list, dict)):
                data_model[f"{item['key']}_{_clean_key(field)}"] = value
        candidate_text = result.get("text")
        if isinstance(candidate_text, str):
            parsed_text = _parse_json_object(candidate_text)
            if parsed_text:
                data_model[f"{item['key']}_data"] = parsed_text
                for field, value in parsed_text.items():
                    data_model[f"{item['key']}_{_clean_key(field)}"] = value
    data_model["subjects"] = [item["label"] for item in outcomes]
    journal = ctx.runtime.graph.events(ctx.run_id)
    data_model["timeline"] = [{"time": str(event.sequence),
                               "label": f"{event.kind} {event.node_id or ''}".strip()}
                              for event in journal]
    succeeded = sum(1 for node in snapshot.nodes.values() if node["state"] == "succeeded")
    data_model["progress_value"] = succeeded
    data_model["progress_max"] = max(1, len(snapshot.nodes))

    # Merge the single-goal content role's GENERIC STRUCTURED answer into
    # the data model under clean, domain-neutral pointers so the compose
    # step can reach for RICH components (charts, cards, tables, choices).
    # Everything optional; only non-empty structure is exposed. For a
    # multi-entity research run content_structured is empty and the
    # outcome-derived arrays above stand. No domain words appear here.
    def _num(value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(str(value).replace(",", "").strip())
        except Exception:
            return None

    if content_structured:
        title = content_structured.get("title")
        if isinstance(title, str) and title.strip():
            data_model["title"] = title.strip()
        intro = content_structured.get("intro")
        if isinstance(intro, str) and intro.strip():
            data_model["intro"] = intro.strip()
            if not summary:
                data_model["summary"] = intro.strip()

        # A surface with inputs needs somewhere to put what the user
        # types. The client's setPointer creates missing paths on write,
        # so an undeclared target happens to work; declaring it makes the
        # write surface visible in the data model instead of appearing
        # the first time somebody clicks something.
        data_model.setdefault("input", {})

        sections = content_structured.get("sections")
        if isinstance(sections, list) and sections:
            clean_sections: list[dict[str, Any]] = []
            for index, section in enumerate(sections):
                if not isinstance(section, dict):
                    continue
                heading = str(section.get("heading") or f"Section {index + 1}").strip()
                points = [str(point).strip() for point in (section.get("points") or []) if str(point).strip()]
                detail = str(section.get("detail") or "").strip()
                clean_sections.append({"heading": heading, "points": points,
                                       "options": points, "detail": detail})
                data_model[f"section_{index}_heading"] = heading
                data_model[f"section_{index}_points"] = "\n".join(f"• {point}" for point in points) or heading
                # The body that belongs to this item, bindable on its own
                # so a surface can put it somewhere the heading is not:
                # a second tab, a later card, a details panel.
                data_model[f"section_{index}_detail"] = detail
                data_model[f"section_{index}_options"] = points
            if clean_sections:
                data_model["sections"] = clean_sections
                # A timeline-shaped view of the ordered sections so a
                # Timeline can bind them: heading as the time, points as
                # the label.
                data_model["section_events"] = [
                    {"time": section["heading"], "label": "; ".join(section["points"])}
                    for section in clean_sections]

        metrics = content_structured.get("metrics")
        if isinstance(metrics, list) and metrics:
            clean_metrics: list[dict[str, Any]] = []
            for metric in metrics:
                if not isinstance(metric, dict) or not str(metric.get("label") or "").strip():
                    continue
                clean_metrics.append({"label": str(metric["label"]).strip(),
                                      "value": metric.get("value"),
                                      "unit": str(metric.get("unit") or "").strip()})
            if clean_metrics:
                data_model["metrics"] = clean_metrics
                for index, metric in enumerate(clean_metrics):
                    data_model[f"metric_{index}_value"] = metric["value"]

        series = content_structured.get("series")
        if isinstance(series, list) and series:
            clean_series, spark = [], []
            for point in series:
                if not isinstance(point, dict):
                    continue
                label = str(point.get("label") or "").strip()
                value = _num(point.get("value"))
                if not label or value is None:
                    continue
                clean_series.append({"label": label, "value": value})
                spark.append(value)
            if clean_series:
                data_model["series"] = clean_series
                data_model["series_values"] = spark
                data_model["spark"] = spark

        table = content_structured.get("table")
        if isinstance(table, dict):
            columns = [str(column).strip() for column in (table.get("columns") or []) if str(column).strip()]
            rows = [row for row in (table.get("rows") or []) if isinstance(row, dict)]
            if columns:
                data_model["table_columns"] = columns
            if rows:
                data_model["table_rows"] = rows

        choices = content_structured.get("choices")
        if isinstance(choices, list) and choices:
            clean_choices: list[dict[str, Any]] = []
            for choice in choices:
                if isinstance(choice, dict) and str(choice.get("label") or "").strip():
                    label = str(choice["label"]).strip()
                    clean_choices.append({"id": str(choice.get("id") or _slug(label)), "label": label})
                elif isinstance(choice, str) and choice.strip():
                    clean_choices.append({"id": _slug(choice), "label": choice.strip()})
            if clean_choices:
                data_model["choices"] = clean_choices
                data_model["subjects"] = [choice["label"] for choice in clean_choices]
                for index, choice in enumerate(clean_choices):
                    data_model[f"choice_{index}_label"] = choice["label"]

    manifest = catalog_manifest()
    pointers = sorted("/" + key for key in data_model)
    # Domain-agnostic system prompt: compose an A2UI interface for the goal
    # that binds to the data model, under the A2UI-Basic shape rules. It
    # says NOTHING about any particular domain, chart, or entity type.
    system = ("You compose declarative A2UI interfaces for a goal, binding every value to a provided "
              'dataModel. Output ONLY one JSON object {"root":"root","components":[...]}. Each component '
              'is a FLAT object whose fields sit DIRECTLY on it: {"id":..., "type":..., <prop>:<value>, '
              '...}. Do NOT wrap fields in a "props" object and do NOT nest a "properties" key. The '
              'catalog uses A2UI Basic names: use "Text" with "variant":"heading" for titles (there is NO '
              '"Heading" type), "Row"/"Column"/"List"/"Card" for layout (there is NO "Grid" type), "Tabs" '
              'whose "children" are the panels directly (there is NO separate "Tab" type), and "Button" '
              'for tappable choices. Shape examples (fields inline): '
              '{"id":"h","type":"Text","variant":"heading","text":{"$bind":"/title"}}  '
              '{"id":"r","type":"Row","align":"stretch","justify":"spaceBetween","children":["a","b"]}  '
              '{"id":"b1","type":"Button","label":"Choice A","onPress":{"action":"request_data"}}  '
              '{"id":"body","type":"Text","variant":"body","text":{"$bind":"/summary"}}  '
              '{"id":"tabs","type":"Tabs","labels":"One,Two","children":["p0","p1"]}. '
              "Use ONLY the component types and props named in the catalog. Every DATA value a component "
              'shows MUST be a binding {"$bind":"/pointer"} into the dataModel; a Button/Card/Tabs '
              "label/title and column names may be literal UI strings. An onPress action MUST be one of the "
              "registered actions (use \"request_data\" for choices); never invent an action, component "
              "type, prop, event handler, URL, or markup. children/labels reference component ids. "
              "Prefer the RICHEST fitting component for each piece of data, NEVER one big Text blob: a "
              "Timeline or a List/Column of Cards for ordered groups, StatTiles in a Row for key numbers, "
              "a BarChart or Sparkline for a numeric series, a DataTable for tabular rows, and Buttons for "
              "tappable choices. Fall back to a single Text only when the data has no structure. Return "
              "JSON only: no prose, no fences.")
    instruction = {
        "goal": ctx.goal,
        "catalog": manifest,
        "dataModel": data_model,
        "available_pointers": pointers,
        "compose": ("Compose the RICHEST interface that serves the goal above, using ONLY catalog types, "
                    "and choose components from the data that is actually present in available_pointers. "
                    'Start with a Text (variant "heading") bound to /title, then a Text (variant "body") '
                    "bound to /intro or /summary if present. Then map the structured data to rich "
                    "components (skip any pointer that is absent): "
                    "for /sections (ordered groups) render EITHER a Timeline bound to /section_events OR a "
                    "List/Column of Cards, one Card per section titled with the literal /section_N_heading "
                    "and a Text bound to /section_N_points; "
                    "for /metrics render a Row of StatTiles, each StatTile value bound to /metric_N_value "
                    "with a literal label; "
                    "for /series render a BarChart (data bound to /series, xKey \"label\", yKey \"value\") "
                    "or a Sparkline bound to /series_values; "
                    "for /table_rows render a DataTable (rows bound to /table_rows, columns the literal "
                    "/table_columns joined by commas); "
                    "for /choices (the goal asks the user to pick) render one tappable Button per entry, "
                    "label the literal /choice_N_label, onPress action \"request_data\"; "
                    "you may also add a ProgressBar bound to /progress_value (max /progress_max) and a "
                    "Timeline bound to /timeline for the run's own steps. Do NOT dump everything into one "
                    "Text. Bind every DATA value to a /pointer listed in available_pointers."),
    }
    body = await surface_llm(json.dumps(instruction), system)
    raw = body.get("text", "")
    surface = _extract_surface(raw)
    proposed = surface.get("components", []) if isinstance(surface, dict) else []
    validation = validate_surface(surface if isinstance(surface, dict) else {"components": []})
    accepted_ids = {comp.get("id") for comp in validation.accepted}
    dangling = sorted({child for comp in validation.accepted
                       for child in comp.get("children", []) if child not in accepted_ids})
    types_used = sorted({comp.get("type") for comp in validation.accepted})
    return {
        "agent": "ui_composer", "provider": body.get("provider"), "model": body.get("model"),
        "raw_surface": raw,
        "surface": {"root": (surface or {}).get("root", "root") if isinstance(surface, dict) else "root",
                    "components": validation.accepted, "dataModel": data_model},
        "data_model": data_model,
        "validator": {"proposed": len(proposed), "accepted": len(validation.accepted),
                      "rejected": len(validation.rejections), "ok": validation.ok,
                      "rejections": [rejection.as_dict() for rejection in validation.rejections],
                      "dangling_child_refs": dangling, "component_types": types_used,
                      "component_count": len(validation.accepted)},
        "upstream_used": [item["label"] for item in outcomes],
        "parse_ok": surface is not None,
    }
