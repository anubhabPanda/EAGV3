"""Journal -> OpenTelemetry spans.

Session 14 turned the durable event journal into AG-UI events. Session 15 turns
the same journal into OTel spans. No parallel event system exists, and none is
needed: the graph already writes the only record either consumer reads.
"""

from .spans import (
    COST,
    CURRENCY,
    GEN_AI_INPUT_TOKENS,
    GEN_AI_OPERATION,
    GEN_AI_OUTPUT_TOKENS,
    GEN_AI_PROVIDER,
    GEN_AI_REQUEST_MODEL,
    SPAN_KIND,
    SpanExport,
    SpanNode,
    build_span_tree,
    build_tracer_provider,
    content_capture_enabled,
    emit_span_tree,
    export_run,
)

__all__ = [
    "COST",
    "CURRENCY",
    "GEN_AI_INPUT_TOKENS",
    "GEN_AI_OPERATION",
    "GEN_AI_OUTPUT_TOKENS",
    "GEN_AI_PROVIDER",
    "GEN_AI_REQUEST_MODEL",
    "SPAN_KIND",
    "SpanExport",
    "SpanNode",
    "build_span_tree",
    "build_tracer_provider",
    "content_capture_enabled",
    "emit_span_tree",
    "export_run",
]
