from __future__ import annotations

import json

import sourcecode.routes as agent_route
import sourcecode.runtime as runtime_module
import sourcecode.workers.general as general_workers
from sourcecode.core.memory.embeddings import DeterministicEmbedder
from sourcecode.tools import file_uri_to_path


def _patch(add=None, reason="next outcome earned this frontier"):
    return {"add": add or [], "cancel": [], "finish": False, "reason": reason}


def _task(node_id, capability, arguments, depends_on=()):
    return {"id": node_id, "capability": capability, "arguments": arguments,
            "depends_on": list(depends_on)}


def _install_agent(monkeypatch, decide, *, answer="grounded answer"):
    async def fake(_app, prompt, system):
        if "evidence-readiness critic" in system:
            return {"text": json.dumps({"ready": True, "missing": [], "reason": "test evidence is complete"}),
                    "provider": "critic-provider", "model": "critic-model"}
        if "decision core of a live-graph agent" in system:
            context = json.loads(prompt)
            return {"text": json.dumps(decide(context)), "provider": "planner-provider", "model": "planner-model"}
        if "researcher role" in system:
            return {"text": "specialist synthesis", "provider": "worker-provider", "model": "worker-model"}
        if "distiller role" in system or "coder_validator role" in system:
            return {"text": "synthesized and validated", "provider": "worker-provider", "model": "worker-model"}
        return {"text": answer, "provider": "answer-provider", "model": "answer-model"}

    monkeypatch.setattr(agent_route, "gateway_text_llm", fake)


def _states(context):
    return {node["id"]: node["state"] for node in context["graph"]["nodes"]}


def _all_terminal(states, prefix):
    selected = [state for node_id, state in states.items() if node_id.startswith(prefix)]
    return selected and all(state in {"succeeded", "failed", "cancelled"} for state in selected)


def test_search_outcome_expands_into_fetches_only_after_urls_exist(app_client, monkeypatch):
    app_client.app.state.runtime.memory.embedder = DeterministicEmbedder(128)

    def decide(context):
        states = _states(context)
        if not states:
            return _patch([_task("discover", "web_search", {"query": "Python asyncio best practices", "max_results": 3})])
        if states.get("discover") == "succeeded" and not any(node.startswith("fetch_") for node in states):
            hits = context["latest_event"]["outcome"]["hits"]
            return _patch([_task(f"fetch_{i}", "fetch_url", {"url": hit["url"]}, ["discover"])
                           for i, hit in enumerate(hits, 1)], "search outcome supplied concrete URLs")
        if _all_terminal(states, "fetch_") and "answer" not in states:
            return _patch([_task("answer", "answer_with_evidence", {"query": context["goal"]},
                                [node for node in states if node.startswith("fetch_") and states[node] == "succeeded"])])
        return _patch(reason="wait for active sibling outcomes")

    _install_agent(monkeypatch, decide)

    async def search(query, max_results=3):
        return {"query": query, "hits": [{"title": f"result {i}", "url": f"https://source/{i}",
                                             "snippet": "async advice"} for i in range(max_results)]}

    async def fetch(url):
        return {"url": url, "status": 200, "content_type": "text/plain", "text": f"content from {url}"}

    monkeypatch.setattr(runtime_module, "web_search", search)
    monkeypatch.setattr(runtime_module, "fetch_url", fetch)
    result = app_client.post("/v1/agent/runs", json={"tenant_id": "t", "project_id": "p",
        "prompt": "Look up current Python asyncio best practices and summarize three reliable sources."}).json()
    patches = [event["payload"]["add"] for event in result["events"] if event["kind"] == "graph_patched"]
    assert patches[0] == ["discover"]
    assert patches[1] == ["fetch_1", "fetch_2", "fetch_3"]
    assert result["status"] == "completed"


def test_directory_discovery_earns_parallel_indexing(app_client, monkeypatch, tmp_path):
    app_client.app.state.runtime.memory.embedder = DeterministicEmbedder(128)
    papers = tmp_path / "papers"
    papers.mkdir()
    for name in ("a.md", "b.md", "c.md"):
        (papers / name).write_text(f"# {name}\nA distinct paper about {name}.")
    monkeypatch.setenv("S17_SANDBOX_ROOT", str(tmp_path))

    def decide(context):
        states = _states(context)
        if not states:
            return _patch([_task("discover_files", "list_directory", {"path": "papers", "suffix": ".md"})])
        if states.get("discover_files") == "succeeded" and not any(node.startswith("index_") for node in states):
            paths = context["latest_event"]["outcome"]["paths"]
            return _patch([_task(f"index_{i}", "index_file", {"path": path}, ["discover_files"])
                           for i, path in enumerate(paths, 1)])
        if _all_terminal(states, "index_") and "answer" not in states:
            parents = [node for node in states if node.startswith("index_") and states[node] == "succeeded"]
            return _patch([_task("answer", "answer_with_evidence", {"query": context["goal"]}, parents)])
        return _patch(reason="wait for active indexing siblings")

    _install_agent(monkeypatch, decide)
    result = app_client.post("/v1/agent/runs", json={"tenant_id": "t", "project_id": "p",
        "prompt": "Please absorb all Markdown documents in papers and report the indexed total.",
        "allowed_side_effects": ["index_file"]}).json()
    starts = [event["node_id"] for event in result["events"] if event["kind"] == "task_started"]
    assert starts[:4] == ["discover_files", "index_1", "index_2", "index_3"]
    assert result["status"] == "completed"


def test_unseen_comparison_launches_independent_agents_then_synthesizes(app_client, monkeypatch):
    app_client.app.state.runtime.memory.embedder = DeterministicEmbedder(128)

    def decide(context):
        states = _states(context)
        if not states:
            return _patch([
                _task("rust", "researcher", {"query": "Rust concurrency model ownership async runtimes", "subject": "Rust"}),
                _task("go", "researcher", {"query": "Go concurrency model goroutines channels", "subject": "Go"}),
            ])
        if states.get("rust") == states.get("go") == "succeeded" and "distill" not in states:
            return _patch([_task("distill", "distiller", {"query": context["goal"]}, ["rust", "go"])])
        if states.get("distill") == "succeeded" and "answer" not in states:
            return _patch([_task("answer", "answer_with_evidence", {"query": context["goal"]}, ["distill"])])
        return _patch(reason="wait for independent specialist")

    _install_agent(monkeypatch, decide)
    async def search(query, max_results=3):
        return {"query": query, "hits": [{"title": query, "url": "https://language.test", "snippet": "evidence"}]}
    monkeypatch.setattr(runtime_module, "web_search", search)
    body = app_client.post("/v1/agent/runs", json={"tenant_id": "t", "project_id": "compare",
        "prompt": "Research Rust and Go, then compare their concurrency models."}).json()
    starts = [event["node_id"] for event in body["events"] if event["kind"] == "task_started"]
    assert starts[:2] == ["go", "rust"]  # executor ordering is stable while both share one frontier
    assert body["graph"]["nodes"]["distill"]["state"] == "succeeded"
    assert body["status"] == "completed"


def test_researcher_never_synthesizes_without_readable_evidence(app_client, monkeypatch):
    app_client.app.state.runtime.memory.embedder = DeterministicEmbedder(128)
    researcher_model_calls = 0

    def decide(context):
        states = _states(context)
        if not states:
            return _patch([_task("research", "researcher", {
                "query": "an intentionally source-less question", "subject": "unknown",
            })])
        if states.get("research") == "succeeded" and "answer" not in states:
            return _patch([_task("answer", "answer_with_evidence", {"query": context["goal"]})])
        return _patch(reason="wait")

    async def fake(_app, prompt, system):
        nonlocal researcher_model_calls
        if "evidence-readiness critic" in system:
            return {"text": json.dumps({"ready": True, "missing": [], "reason": "test-only"})}
        if "decision core of a live-graph agent" in system:
            return {"text": json.dumps(decide(json.loads(prompt)))}
        if "bounded research agent" in system:
            researcher_model_calls += 1
        return {"text": "The search failed, so no factual claim can be made."}

    async def empty_search(query, max_results=3):
        return {"query": query, "hits": [], "backend": None, "errors": ["all backends unavailable"]}

    monkeypatch.setattr(agent_route, "gateway_text_llm", fake)
    # run_researcher moved to workers/general.py, so that is where the symbol
    # it calls now lives. The behaviour under test is unchanged; the patch
    # target was coupled to which module happened to import the tool.
    monkeypatch.setattr(general_workers, "web_search", empty_search)
    body = app_client.post("/v1/agent/runs", json={"tenant_id": "t", "project_id": "no-evidence",
        "prompt": "Research a current fact whose sources are unavailable."}).json()
    result = body["graph"]["nodes"]["research"]["result"]
    assert result["insufficient"] is True
    assert result["text"] == ""
    assert researcher_model_calls == 0


def test_calendar_skill_is_general_and_uses_planner_supplied_iso_dates(app_client, monkeypatch):
    app_client.app.state.runtime.memory.embedder = DeterministicEmbedder(128)

    def decide(context):
        states = _states(context)
        if not states:
            return _patch([
                _task("remember_date", "remember_explicit_fact", {"text": "Mom's birthday is 15 May 2026."}),
                _task("calendar", "create_calendar_events", {
                    "title": "Mom's birthday", "dates": ["2026-05-01", "2026-05-15"]}),
            ])
        if states.get("remember_date") == states.get("calendar") == "succeeded" and "answer" not in states:
            return _patch([_task("answer", "answer_with_evidence", {"query": context["goal"]},
                                ["remember_date", "calendar"])])
        return _patch(reason="wait for requested side effects")

    _install_agent(monkeypatch, decide)
    body = app_client.post("/v1/agent/runs", json={"tenant_id": "t", "project_id": "birthday",
        "prompt": "My mom's birthday is 15 May 2026. Remember it and make reminders two weeks before and that day.",
        "allowed_side_effects": ["remember_explicit_fact", "create_calendar_events"]}).json()
    artifacts = body["graph"]["nodes"]["calendar"]["result"]["artifacts"]
    assert len(artifacts) == 2
    assert all(file_uri_to_path(uri).read_text().startswith("BEGIN:VCALENDAR") for uri in artifacts)


def test_verify_artifact_reads_back_its_own_file_uri(app_client, monkeypatch):
    """verify_artifact must be able to read the exact file:// URI a prior node in
    the same run just handed it. On Windows, ``Path("C:/x").as_uri()`` produces a
    triple-slash URI (``file:///C:/x``) because the drive letter needs its own
    leading slash; run_verify_artifact converted that back with
    ``Path(str(httpx.URL(uri).path))``, which leaves a bare leading slash in
    front of the drive letter (``/C:/x``) that pathlib refuses to treat as
    drive-rooted. The artifact genuinely exists and is genuinely owned by this
    run, so a PermissionError here is a false refusal, not a real control."""
    app_client.app.state.runtime.memory.embedder = DeterministicEmbedder(128)

    def decide(context):
        states = _states(context)
        if not states:
            return _patch([_task("calendar", "create_calendar_events", {
                "title": "Mom's birthday", "dates": ["2026-05-15"]})])
        if states.get("calendar") == "succeeded" and "verify" not in states:
            uri = context["latest_event"]["outcome"]["artifacts"][0]
            return _patch([_task("verify", "verify_artifact", {"uri": uri}, ["calendar"])])
        if states.get("verify") == "succeeded" and "answer" not in states:
            return _patch([_task("answer", "answer_with_evidence", {"query": context["goal"]},
                                ["calendar", "verify"])])
        return _patch(reason="wait for requested side effects")

    _install_agent(monkeypatch, decide)
    body = app_client.post("/v1/agent/runs", json={"tenant_id": "t", "project_id": "birthday",
        "prompt": "My mom's birthday is 15 May 2026. Make a reminder that day.",
        "allowed_side_effects": ["create_calendar_events"]}).json()
    verify_node = body["graph"]["nodes"]["verify"]
    assert verify_node["state"] == "succeeded", verify_node.get("result")
    assert verify_node["result"]["text"].startswith("BEGIN:VCALENDAR")


def test_failed_file_read_is_visible_to_the_final_answer(app_client, monkeypatch, tmp_path):
    app_client.app.state.runtime.memory.embedder = DeterministicEmbedder(128)
    monkeypatch.setenv("S17_SANDBOX_ROOT", str(tmp_path))

    def decide(context):
        states = _states(context)
        if not states:
            return _patch([_task("attempt_read", "read_file", {"path": "missing.txt"})])
        if states.get("attempt_read") == "failed" and "answer" not in states:
            return _patch([_task("answer", "answer_with_evidence", {"query": context["goal"]})],
                          "explain the visible tool failure")
        return _patch(reason="wait")

    _install_agent(monkeypatch, decide, answer="The requested file does not exist in the sandbox.")
    body = app_client.post("/v1/agent/runs", json={"tenant_id": "t", "project_id": "failure",
        "prompt": "Open missing.txt and report its contents."}).json()
    assert body["graph"]["nodes"]["attempt_read"]["state"] == "failed"
    assert "does not exist" in body["answer"]
