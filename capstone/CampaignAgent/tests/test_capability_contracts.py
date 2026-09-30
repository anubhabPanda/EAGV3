"""Guards on the property the session claims: nothing is special-cased by name.

These are deliberately *behavioural* guards rather than greps. The question is
not "does the string appear somewhere" but "can a capability nobody anticipated
get first-class treatment without anyone editing a generic component". A grep
passes the moment somebody renames a variable; these fail the moment the
property stops holding.
"""
from __future__ import annotations

import pytest

from sourcecode.capabilities import (
    Argument,
    Capability,
    CapabilityError,
    CapabilityRegistry,
    EvidenceProjection,
    default_registry,
    generic_evidence,
    project_evidence,
)


def test_a_url_argument_is_validated_because_it_declared_a_format() -> None:
    """A capability nobody has seen before still gets scheme validation."""
    registry = CapabilityRegistry([
        Capability("post_receipt", "Send a receipt somewhere.",
                   {"endpoint": Argument("string", "Where to post.", maximum=500, format="url")}),
    ])
    assert registry.validate("post_receipt", {"endpoint": "https://example.invalid/hook"})
    for hostile in ("file:///etc/passwd", "gopher://example.invalid", "not-a-url"):
        with pytest.raises(CapabilityError, match="absolute http"):
            registry.validate("post_receipt", {"endpoint": hostile})


def test_every_shipped_url_argument_actually_declares_the_format() -> None:
    """The old code validated three URLs by name; anything else slipped through."""
    for capability in default_registry()._items.values():  # noqa: SLF001
        for name, argument in capability.arguments.items():
            looks_like_url = name in {"url", "endpoint", "agent_url"} or "URL" in argument.description
            if looks_like_url:
                assert argument.format == "url", (
                    f"{capability.name}.{name} accepts a URL but declares no format"
                )


def test_a_new_capability_gets_the_same_evidence_quality_as_a_builtin() -> None:
    """The property that makes assignment Part 2 honest.

    Before the projection was declarative, a capability the answer worker had
    never heard of was dumped as raw JSON with an internal graph:// source. A
    student's capability was therefore worse evidence than a shipped one, for no
    reason the student could see.
    """
    projection = EvidenceProjection(kind="ticket", text="body", sources=("permalink",))
    produced = project_evidence(projection, {"body": "Disk is full on node 3.",
                                             "permalink": "https://tracker.invalid/T-9"},
                                fallback_source="graph://run/node")
    assert produced == [{"text": "Disk is full on node 3.",
                         "sources": ["https://tracker.invalid/T-9"], "kind": "ticket"}]


def test_an_undeclared_capability_result_is_still_never_silently_lost() -> None:
    record = generic_evidence({"total": 3, "uri": "file://out.txt", "raw": "drop me"},
                              skill="mystery", fallback_source="graph://run/node",
                              drop=("raw",))
    assert "raw" not in record["text"]
    assert record["sources"] == ["file://out.txt"]
    assert record["kind"] == "capability:mystery"


def test_expanded_items_are_attributed_individually() -> None:
    projection = EvidenceProjection(items="hits", item_text=("title", "snippet"),
                                    item_source="url", item_kind="search_result")
    produced = project_evidence(projection, {"hits": [
        {"title": "A", "snippet": "one", "url": "https://a.invalid"},
        {"title": "B", "snippet": "two", "url": "https://b.invalid"},
    ]}, fallback_source="graph://run/node")
    assert [item["sources"] for item in produced] == [["https://a.invalid"], ["https://b.invalid"]]
    assert {item["kind"] for item in produced} == {"search_result"}


def test_an_empty_item_list_falls_back_to_its_declared_summary() -> None:
    projection = EvidenceProjection(kind="indexed_chunk", items="manifest", item_text=("text",),
                                    sources=("source_uri",), summary_kind="index_report",
                                    summary="Indexed {chunks} semantic chunks from this document.")
    produced = project_evidence(projection, {"manifest": [], "chunks": 4,
                                             "source_uri": "file://handbook.md"},
                                fallback_source="graph://run/node")
    assert produced == [{"text": "Indexed 4 semantic chunks from this document.",
                         "sources": ["file://handbook.md"], "kind": "index_report"}]


def test_families_replace_the_literal_name_sets_components_used_to_carry() -> None:
    registry = default_registry()
    evidence = registry.family("evidence")
    assert {"web_search", "fetch_url", "researcher"} <= evidence
    # The point of the family: a capability added later joins by declaring it,
    # without any component's hardcoded set being edited.
    extended = CapabilityRegistry(list(registry._items.values()) + [  # noqa: SLF001
        Capability("search_arxiv", "Search preprints.",
                   {"query": Argument("string", "Query.", maximum=100)}, families=("evidence",)),
    ])
    assert "search_arxiv" in extended.family("evidence")


def test_every_registered_capability_has_a_worker_and_every_worker_is_registered() -> None:
    """Catches a worker bound to a capability that no longer exists.

    `formatter` survived for exactly this reason: a role worker was registered
    for a capability that had been removed from the registry, so two branches of
    dead code kept referring to a capability the planner could never choose.
    """
    import asyncio

    import sourcecode.runtime as runtime_module
    from sourcecode.core.memory import MemoryScope

    captured: set[str] = set()

    class _Stop(Exception):
        pass

    original_executor = runtime_module.LiveGraphExecutor

    class _Probe(original_executor):  # type: ignore[misc,valid-type]
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            for candidate in list(args) + list(kwargs.values()):
                if isinstance(candidate, dict) and candidate:
                    captured.update(str(key) for key in candidate)
            raise _Stop

    async def never(prompt: str, system: str):  # noqa: ANN202, ARG001
        raise AssertionError("the probe must not reach a model")

    runtime = runtime_module.AgentRuntime()
    runtime_module.LiveGraphExecutor = _Probe
    try:
        with pytest.raises(_Stop):
            asyncio.run(runtime.run(prompt="probe", scope=MemoryScope("t", "p", "u", "a"),
                                    llm=never, source_uri="test://probe", source_author="test"))
        registered = set(runtime.registry.names())
        workers = captured & (registered | {"formatter"})
        assert workers - registered == set(), f"workers with no capability: {workers - registered}"
        assert registered - captured == set(), f"capabilities with no worker: {registered - captured}"
    finally:
        runtime_module.LiveGraphExecutor = original_executor
        runtime.close()
