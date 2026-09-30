"""Turn the durable event journal into OpenTelemetry spans.

The elegant part of this session is that nothing new is recorded. Session 13
wrote one durable journal per run; Session 14 translated it into AG-UI events for
a browser; Session 15 translates the *same* journal into OTel spans for a
collector. One tape, three readers — graph replay, UI stream, trace export.

The hierarchy the spec asks for falls straight out of the journal:

    run                     the whole tape for one run_id
    └── agent loop          one planning round (a graph_patched event)
        ├── plan            what the planner decided, and why
        └── node            a task, from task_started to its terminal event
            └── provider call   one metered model call inside that task

Attributes follow the OTel GenAI semantic conventions (``gen_ai.provider.name``,
``gen_ai.request.model``, ``gen_ai.usage.input_tokens``,
``gen_ai.usage.output_tokens``, ``gen_ai.operation.name``). Those conventions are
pre-stable and moved to their own repository in June 2026 with no tagged release,
so cost has no blessed attribute yet: it is emitted under the vendor-prefixed
``s15.cost`` alongside ``s15.currency``, and clearly marked as an extension.

**Content capture is off by default.** Prompts and completions are PII; they are
attached only when the caller opts in (``capture_content=True`` or a truthy
``S17_OTEL_CAPTURE_CONTENT``).

The exporter endpoint is configuration. With none set the module still builds a
complete, assertable span tree in memory and exports nothing over the wire, so
tests and CI need no collector.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from ..economics.controller import DECISION_KEY, METER_KEY

# --- attribute names ------------------------------------------------------- #

GEN_AI_OPERATION = "gen_ai.operation.name"
GEN_AI_PROVIDER = "gen_ai.provider.name"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
GEN_AI_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
GEN_AI_AGENT_NAME = "gen_ai.agent.name"
GEN_AI_TOOL_NAME = "gen_ai.tool.name"
GEN_AI_INPUT_MESSAGES = "gen_ai.input.messages"
GEN_AI_OUTPUT_MESSAGES = "gen_ai.output.messages"

#: Cost is not in the GenAI conventions yet, so it carries a vendor prefix.
COST = "s15.cost"
CURRENCY = "s15.currency"

SPAN_KIND = "s15.span.kind"
RUN_ID = "s15.run.id"
PRINCIPAL = "s15.principal"
NODE_ID = "s15.node.id"
NODE_STATE = "s15.node.state"
NODE_TIER = "s15.tier"
BUDGET_TOTAL = "s15.budget.total"
BUDGET_SPENT = "s15.budget.spent"
BUDGET_REMAINING = "s15.budget.remaining"
BUDGET_DECISION = "s15.budget.decision"

#: Journal event kinds that terminate a node span.
TERMINAL_KINDS = ("task_succeeded", "task_failed", "task_cancelled")

CAPTURE_CONTENT_ENV = "S17_OTEL_CAPTURE_CONTENT"
ENDPOINT_ENV = "S17_OTEL_EXPORTER_ENDPOINT"
SERVICE_NAME_ENV = "S17_OTEL_SERVICE_NAME"
DEFAULT_SERVICE_NAME = "sourcecode"

#: Synthetic clock step, in seconds, for spans the journal cannot time. The
#: journal records order, not wall clock; provider-call spans carry real
#: timestamps and durations because the meter records them.
SEQUENCE_TICK_SECONDS = 0.001


def content_capture_enabled(explicit: bool | None = None) -> bool:
    if explicit is not None:
        return explicit
    return os.getenv(CAPTURE_CONTENT_ENV, "0").strip().lower() in {"1", "true", "yes", "on"}


# --- the span tree --------------------------------------------------------- #


@dataclass
class SpanNode:
    """One span, before it is handed to the SDK."""

    name: str
    kind: str
    attributes: dict[str, Any] = field(default_factory=dict)
    children: list[SpanNode] = field(default_factory=list)
    start_ns: int | None = None
    end_ns: int | None = None
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    status_error: str | None = None

    def add(self, child: SpanNode) -> SpanNode:
        self.children.append(child)
        return child

    def resolve_times(self, fallback_start_ns: int, fallback_end_ns: int) -> tuple[int, int]:
        """Bottom-up bounds: a parent covers its children, leaves use their own."""
        for child in self.children:
            child.resolve_times(self.start_ns or fallback_start_ns, self.end_ns or fallback_end_ns)
        starts = [c.start_ns for c in self.children if c.start_ns is not None]
        ends = [c.end_ns for c in self.children if c.end_ns is not None]
        if self.start_ns is None:
            self.start_ns = min(starts) if starts else fallback_start_ns
        elif starts:
            self.start_ns = min([self.start_ns, *starts])
        if self.end_ns is None:
            self.end_ns = max(ends) if ends else fallback_end_ns
        elif ends:
            self.end_ns = max([self.end_ns, *ends])
        if self.end_ns < self.start_ns:
            self.end_ns = self.start_ns
        return self.start_ns, self.end_ns

    def walk(self) -> Iterable[SpanNode]:
        yield self
        for child in self.children:
            yield from child.walk()


def _num(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def build_span_tree(
    run: dict[str, Any],
    *,
    budget: dict[str, Any] | None = None,
    capture_content: bool | None = None,
    principal: str | None = None,
    tick_seconds: float = SEQUENCE_TICK_SECONDS,
) -> SpanNode:
    """Build ``run -> agent loop -> plan -> node -> provider call`` from a journal.

    ``run`` is the journal shape the runtime and the UI already pass around:
    ``{run_id, finished, nodes, edges, events}`` with events as
    ``{sequence, kind, node_id, payload}``. Nothing else is required, so a
    recorded fixture traces exactly like a live run.
    """
    capture = content_capture_enabled(capture_content)
    events: Sequence[dict[str, Any]] = list(run.get("events") or [])
    nodes: dict[str, Any] = run.get("nodes") or {}
    run_id = run.get("run_id") or "unknown-run"
    snapshot = budget or {}
    who = principal or snapshot.get("principal")

    # The journal orders events but does not time them. Real timestamps exist
    # wherever the meter recorded one, so anchor the synthetic clock to the first
    # real call and lay unmeasured spans out in sequence order around it.
    real_starts = [
        _num(call.get("started_at"))
        for event in events
        for call in (event.get("payload") or {}).get(METER_KEY) or []
        if _num(call.get("started_at")) > 0
    ]
    base = min(real_starts) if real_starts else time.time()
    first_seq = events[0]["sequence"] if events else 0

    def clock(sequence: int) -> int:
        return int((base + (sequence - first_seq) * tick_seconds) * 1_000_000_000)

    root = SpanNode(
        name=f"run {run_id}",
        kind="run",
        attributes={
            SPAN_KIND: "run",
            RUN_ID: run_id,
            GEN_AI_OPERATION: "invoke_agent",
            GEN_AI_AGENT_NAME: str(run.get("agent") or DEFAULT_SERVICE_NAME),
            "s15.run.finished": bool(run.get("finished")),
            "s15.journal.events": len(events),
        },
        start_ns=clock(first_seq),
    )
    if who:
        root.attributes[PRINCIPAL] = who
    if snapshot:
        root.attributes.update(
            {
                BUDGET_TOTAL: _num(snapshot.get("total")),
                BUDGET_SPENT: _num(snapshot.get("spent")),
                BUDGET_REMAINING: _num(snapshot.get("remaining")),
                CURRENCY: snapshot.get("currency", "USD"),
                "s15.budget.refusals": int(snapshot.get("refusals") or 0),
                "s15.budget.downgrades": int(snapshot.get("downgrades") or 0),
            }
        )
        # A refused call never became a provider span, so the run span carries the
        # refusals as events. An exhausted budget must be visible in the trace,
        # not inferable from an absence.
        for refusal in snapshot.get("refusal_log") or []:
            root.events.append(("budget.refused", {
                NODE_ID: str(refusal.get("node_id") or ""),
                "s15.budget.reason": str(refusal.get("reason") or ""),
                BUDGET_SPENT: _num(refusal.get("spent")),
                BUDGET_REMAINING: _num(refusal.get("remaining")),
            }))

    loops: list[SpanNode] = []
    node_to_loop: dict[str, SpanNode] = {}
    open_nodes: dict[str, SpanNode] = {}
    total_cost = 0.0
    provider_calls = 0

    def current_loop(sequence: int) -> SpanNode:
        """The round a node belongs to; runs always have at least one."""
        if not loops:
            loops.append(
                root.add(
                    SpanNode(
                        name="agent loop 1",
                        kind="agent_loop",
                        attributes={SPAN_KIND: "agent_loop", GEN_AI_OPERATION: "invoke_agent",
                                    "s15.loop.round": 1},
                        start_ns=clock(sequence),
                    )
                )
            )
        return loops[-1]

    for event in events:
        kind = event.get("kind")
        sequence = int(event.get("sequence", 0))
        node_id = event.get("node_id")
        payload = event.get("payload") or {}

        if kind == "graph_patched":
            loop = root.add(
                SpanNode(
                    name=f"agent loop {len(loops) + 1}",
                    kind="agent_loop",
                    attributes={
                        SPAN_KIND: "agent_loop",
                        GEN_AI_OPERATION: "invoke_agent",
                        "s15.loop.round": len(loops) + 1,
                        "s15.loop.trigger_event": int(payload.get("trigger_event") or 0),
                    },
                    start_ns=clock(sequence),
                )
            )
            loops.append(loop)
            added = [str(item) for item in (payload.get("add") or [])]
            plan_span = loop.add(
                SpanNode(
                    name="plan",
                    kind="plan",
                    attributes={
                        SPAN_KIND: "plan",
                        GEN_AI_OPERATION: "invoke_agent",
                        "s15.plan.reason": str(payload.get("reason") or ""),
                        "s15.plan.added": ",".join(added),
                        "s15.plan.added_count": len(added),
                        "s15.plan.cancelled": ",".join(str(i) for i in (payload.get("cancel") or [])),
                        "s15.plan.finish": bool(payload.get("finish")),
                    },
                    start_ns=clock(sequence),
                    end_ns=clock(sequence),
                )
            )
            for decision in payload.get(DECISION_KEY) or []:
                plan_span.events.append(("budget.decision", {
                    BUDGET_DECISION: str(decision.get("action") or ""),
                    "s15.budget.reason": str(decision.get("reason") or ""),
                    NODE_TIER: str(decision.get("tier") or ""),
                }))
            for index, call in enumerate(payload.get(METER_KEY) or [], start=1):
                provider_calls += 1
                cost = _num(call.get("cost"))
                total_cost += cost
                started = _num(call.get("started_at"))
                latency = _num(call.get("latency_ms"))
                call_start = int(started * 1_000_000_000) if started > 0 else clock(sequence)
                plan_span.add(SpanNode(
                    name=f"planner chat {call.get('model') or 'model'}",
                    kind="provider_call",
                    attributes={
                        SPAN_KIND: "provider_call", GEN_AI_OPERATION: "chat",
                        GEN_AI_PROVIDER: str(call.get("provider") or "unknown"),
                        GEN_AI_REQUEST_MODEL: str(call.get("requested_model") or call.get("model") or "unknown"),
                        GEN_AI_RESPONSE_MODEL: str(call.get("model") or "unknown"),
                        GEN_AI_INPUT_TOKENS: int(call.get("input_tokens") or 0),
                        GEN_AI_OUTPUT_TOKENS: int(call.get("output_tokens") or 0),
                        COST: cost, CURRENCY: snapshot.get("currency", "USD"),
                        NODE_TIER: str(call.get("tier") or ""),
                        NODE_ID: str(call.get("node_id") or f"plan_{index}"),
                        BUDGET_DECISION: str(call.get("decision") or "proceed"),
                        BUDGET_REMAINING: _num(call.get("budget_remaining")),
                    },
                    start_ns=call_start,
                    end_ns=call_start + int(latency * 1_000_000),
                ))
            for added_id in added:
                node_to_loop[added_id] = loop
            continue

        if kind == "task_started" and node_id:
            parent = node_to_loop.get(node_id) or current_loop(sequence)
            skill = str(payload.get("skill") or (nodes.get(node_id) or {}).get("skill") or node_id)
            agent = str(payload.get("agent") or skill)
            metadata = (nodes.get(node_id) or {}).get("metadata") or {}
            span = parent.add(
                SpanNode(
                    name=f"node {node_id}",
                    kind="node",
                    attributes={
                        SPAN_KIND: "node",
                        GEN_AI_OPERATION: "execute_tool",
                        GEN_AI_TOOL_NAME: skill,
                        GEN_AI_AGENT_NAME: agent,
                        NODE_ID: node_id,
                        RUN_ID: run_id,
                    },
                    start_ns=clock(sequence),
                )
            )
            if metadata.get("tier"):
                span.attributes[NODE_TIER] = str(metadata["tier"])
            open_nodes[node_id] = span
            continue

        if kind in TERMINAL_KINDS and node_id:
            span = open_nodes.pop(node_id, None)
            if span is None:
                # Cancelled before it ever ran: still worth a span, so the trace
                # shows the graph's decision rather than a silent gap.
                parent = node_to_loop.get(node_id) or current_loop(sequence)
                span = parent.add(
                    SpanNode(
                        name=f"node {node_id}",
                        kind="node",
                        attributes={SPAN_KIND: "node", GEN_AI_OPERATION: "execute_tool",
                                    NODE_ID: node_id, RUN_ID: run_id},
                        start_ns=clock(sequence),
                    )
                )
            state = {"task_succeeded": "succeeded", "task_failed": "failed",
                     "task_cancelled": "cancelled"}[str(kind)]
            span.attributes[NODE_STATE] = state
            span.end_ns = clock(sequence)
            if kind == "task_failed":
                span.status_error = str(payload.get("error") or "task failed")
            if kind == "task_cancelled":
                span.attributes["s15.node.cancel_reason"] = str(payload.get("reason") or "")

            for decision in payload.get(DECISION_KEY) or []:
                span.events.append(("budget.decision", {
                    BUDGET_DECISION: str(decision.get("action") or ""),
                    "s15.budget.reason": str(decision.get("reason") or ""),
                    NODE_TIER: str(decision.get("tier") or ""),
                    "s15.tier.requested": str(decision.get("requested_tier") or ""),
                    "s15.budget.projected_cost": _num(decision.get("projected_cost")),
                }))

            for index, call in enumerate(payload.get(METER_KEY) or [], start=1):
                provider_calls += 1
                cost = _num(call.get("cost"))
                total_cost += cost
                started = _num(call.get("started_at"))
                latency = _num(call.get("latency_ms"))
                call_start = int(started * 1_000_000_000) if started > 0 else clock(sequence)
                attributes: dict[str, Any] = {
                    SPAN_KIND: "provider_call",
                    GEN_AI_OPERATION: "chat",
                    GEN_AI_PROVIDER: str(call.get("provider") or "unknown"),
                    GEN_AI_REQUEST_MODEL: str(call.get("requested_model") or call.get("model") or "unknown"),
                    GEN_AI_RESPONSE_MODEL: str(call.get("model") or "unknown"),
                    GEN_AI_INPUT_TOKENS: int(call.get("input_tokens") or 0),
                    GEN_AI_OUTPUT_TOKENS: int(call.get("output_tokens") or 0),
                    COST: cost,
                    CURRENCY: snapshot.get("currency", "USD"),
                    NODE_TIER: str(call.get("tier") or ""),
                    NODE_ID: node_id,
                    BUDGET_DECISION: str(call.get("decision") or "proceed"),
                    BUDGET_REMAINING: _num(call.get("budget_remaining")),
                    "s15.cost.projected": _num(call.get("projected_cost")),
                }
                if call.get("reasoning"):
                    attributes["gen_ai.request.reasoning_effort"] = str(call["reasoning"])
                if call.get("cache_read_tokens"):
                    attributes["gen_ai.usage.cache_read_input_tokens"] = int(call["cache_read_tokens"])
                if capture:
                    # Opt-in only: prompts and completions are PII.
                    if call.get("prompt"):
                        attributes[GEN_AI_INPUT_MESSAGES] = str(call["prompt"])
                    if call.get("completion"):
                        attributes[GEN_AI_OUTPUT_MESSAGES] = str(call["completion"])
                span.add(
                    SpanNode(
                        name=f"chat {call.get('model') or 'model'}",
                        kind="provider_call",
                        attributes=attributes,
                        start_ns=call_start,
                        end_ns=call_start + int(max(latency, 0.0) * 1_000_000),
                    )
                )
            continue

    last_seq = events[-1]["sequence"] if events else first_seq
    root.attributes.update({
        "s15.provider_calls": provider_calls,
        "s15.loops": len(loops),
        COST: total_cost,
    })
    root.resolve_times(clock(first_seq), clock(last_seq))
    return root


# --- exporting ------------------------------------------------------------- #


def _otlp_exporter(endpoint: str):  # pragma: no cover - needs a collector to matter
    """An OTLP exporter for ``endpoint``: HTTP for a URL, gRPC otherwise."""
    if endpoint.startswith(("http://", "https://")):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        return OTLPSpanExporter(endpoint=endpoint)
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter as GrpcExporter

    return GrpcExporter(endpoint=endpoint, insecure=True)


@dataclass
class SpanExport:
    """What an export produced: the spans, the totals, and where they went."""

    tree: SpanNode
    spans: tuple[ReadableSpan, ...]
    endpoint: str | None
    service_name: str
    capture_content: bool
    exported_over_the_wire: bool

    def by_kind(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for span in self.spans:
            kind = str((span.attributes or {}).get(SPAN_KIND, "unknown"))
            counts[kind] = counts.get(kind, 0) + 1
        return counts

    def provider_call_spans(self) -> tuple[ReadableSpan, ...]:
        return tuple(
            span for span in self.spans
            if (span.attributes or {}).get(SPAN_KIND) == "provider_call"
        )

    def totals(self) -> dict[str, Any]:
        calls = self.provider_call_spans()
        return {
            "spans": len(self.spans),
            "by_kind": self.by_kind(),
            "provider_calls": len(calls),
            "input_tokens": sum(int((s.attributes or {}).get(GEN_AI_INPUT_TOKENS, 0)) for s in calls),
            "output_tokens": sum(int((s.attributes or {}).get(GEN_AI_OUTPUT_TOKENS, 0)) for s in calls),
            "cost": sum(float((s.attributes or {}).get(COST, 0.0)) for s in calls),
            "trace_ids": sorted({format(s.context.trace_id, "032x") for s in self.spans if s.context}),
        }

    def as_dict(self) -> dict[str, Any]:
        """A JSON-safe rendering: the span tree a proof or a waterfall widget reads."""
        return {
            "endpoint": self.endpoint,
            "service_name": self.service_name,
            "capture_content": self.capture_content,
            "exported_over_the_wire": self.exported_over_the_wire,
            "totals": self.totals(),
            "spans": [
                {
                    "name": span.name,
                    "kind": str((span.attributes or {}).get(SPAN_KIND, "unknown")),
                    "span_id": format(span.context.span_id, "016x") if span.context else None,
                    "parent_span_id": format(span.parent.span_id, "016x") if span.parent else None,
                    "trace_id": format(span.context.trace_id, "032x") if span.context else None,
                    "start_time": span.start_time,
                    "end_time": span.end_time,
                    "duration_ns": (span.end_time or 0) - (span.start_time or 0),
                    "status": span.status.status_code.name if span.status else "UNSET",
                    "attributes": dict(span.attributes or {}),
                    "events": [
                        {"name": e.name, "attributes": dict(e.attributes or {})} for e in span.events
                    ],
                }
                for span in self.spans
            ],
        }


def build_tracer_provider(
    *,
    endpoint: str | None = None,
    service_name: str | None = None,
    resource_attributes: dict[str, Any] | None = None,
) -> tuple[TracerProvider, InMemorySpanExporter, bool]:
    """A provider that always records in memory and exports only when configured.

    The in-memory exporter is what makes this testable with no collector running;
    the OTLP exporter is added only when an endpoint is configured, so an unset
    endpoint is a genuine no-op rather than a connection error.
    """
    name = service_name or os.getenv(SERVICE_NAME_ENV) or DEFAULT_SERVICE_NAME
    resource = Resource.create({"service.name": name, **(resource_attributes or {})})
    provider = TracerProvider(resource=resource)
    memory = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(memory))

    target = endpoint if endpoint is not None else os.getenv(ENDPOINT_ENV)
    wired = False
    if target:
        provider.add_span_processor(SimpleSpanProcessor(_otlp_exporter(target)))
        wired = True
    return provider, memory, wired


def emit_span_tree(
    tree: SpanNode,
    *,
    tracer_provider: TracerProvider,
    instrumentation_name: str = "sourcecode.telemetry",
) -> None:
    """Walk the tree and record it through the SDK, parents before children."""
    tracer = tracer_provider.get_tracer(instrumentation_name)

    def emit(node: SpanNode, parent_context: Any) -> None:
        span = tracer.start_span(
            node.name,
            context=parent_context,
            start_time=node.start_ns,
            attributes=node.attributes,
        )
        if node.status_error:
            span.set_status(trace.Status(trace.StatusCode.ERROR, node.status_error))
        for name, attributes in node.events:
            span.add_event(name, attributes=attributes)
        child_context = trace.set_span_in_context(span)
        for child in node.children:
            emit(child, child_context)
        span.end(end_time=node.end_ns)

    emit(tree, trace.set_span_in_context(trace.INVALID_SPAN))


def export_run(
    run: dict[str, Any],
    *,
    budget: dict[str, Any] | None = None,
    endpoint: str | None = None,
    service_name: str | None = None,
    capture_content: bool | None = None,
    principal: str | None = None,
    resource_attributes: dict[str, Any] | None = None,
) -> SpanExport:
    """Journal in, spans out. The one call a proof or a route needs."""
    tree = build_span_tree(run, budget=budget, capture_content=capture_content, principal=principal)
    provider, memory, wired = build_tracer_provider(
        endpoint=endpoint, service_name=service_name, resource_attributes=resource_attributes
    )
    emit_span_tree(tree, tracer_provider=provider)
    provider.force_flush()
    export = SpanExport(
        tree=tree,
        spans=tuple(memory.get_finished_spans()),
        endpoint=endpoint if endpoint is not None else os.getenv(ENDPOINT_ENV),
        service_name=(
            service_name or os.getenv(SERVICE_NAME_ENV) or DEFAULT_SERVICE_NAME
        ),
        capture_content=content_capture_enabled(capture_content),
        exported_over_the_wire=wired,
    )
    provider.shutdown()
    return export
