"""Session 8 — growing-graph orchestrator.

The agent's loop becomes a NetworkX DiGraph. Each node is a skill; edges
carry typed AgentResult payloads. The graph GROWS at runtime via five
actors: the Planner's seed plan, dynamic successors from any skill,
static `internal_successors` from the yaml, Critic auto-insertion on
edges out of `critic:true` skills, and Planner re-invocation on node
failure (gated by `recovery.plan_recovery`). Perception's tool-blindness
contract from S7 is preserved — Planner names skills, never tools.

Persistence lives in persistence.py; skill execution in skills.py;
failure-policy in recovery.py; sandbox in sandbox.py.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import networkx as nx

import memory as memory_svc
from gateway import ensure_gateway
from persistence import SessionStore
from recovery import handle_critic_verdict, plan_recovery
from schemas import AgentResult, NodeState
from skills import SkillRegistry, run_skill
from tracer import Session8Tracer
from dotenv import load_dotenv
load_dotenv()

MAX_NODES = 60  # hard cap so a Planner loop cannot grow forever


# ── Graph ────────────────────────────────────────────────────────────────────

class Graph:
    """NetworkX DiGraph wrapper. Nodes are str ids `n:<i>`; each node carries
    `skill`, `inputs` (list of str), and `status`."""

    def __init__(self):
        self.g = nx.DiGraph()
        self._counter = 0

    def add_node(self, skill: str, inputs: list[str], metadata: dict | None = None) -> str:
        self._counter += 1
        nid = f"n:{self._counter}"
        self.g.add_node(nid, skill=skill, inputs=list(inputs),
                        metadata=dict(metadata or {}), status="pending")
        for inp in inputs:
            if inp.startswith("n:") and inp in self.g.nodes:
                self.g.add_edge(inp, nid)
        return nid

    def mark(self, nid: str, status: str) -> None:
        self.g.nodes[nid]["status"] = status

    def ready_nodes(self) -> list[str]:
        # A predecessor counts as "satisfied" when it is either complete or
        # skipped (the latter is how a Critic-fail removes a child from the
        # critical path without blocking unrelated branches downstream).
        out = []
        for nid, d in self.g.nodes(data=True):
            if d["status"] != "pending":
                continue
            preds = list(self.g.predecessors(nid))
            if all(self.g.nodes[p]["status"] in ("complete", "skipped") for p in preds):
                out.append(nid)
        return out

    def has_running(self) -> bool:
        return any(d["status"] == "running" for _, d in self.g.nodes(data=True))

    def extend_from(self, src_nid: str, result: AgentResult,
                    *, registry: SkillRegistry) -> list[str]:
        """Splice in dynamic successors, static internal_successors, and
        critic auto-insertion. Returns the list of new node ids.

        Resolves label-based input references (`n:<label>`) against the
        `metadata.label` of nodes added in the same batch. The Planner is
        encouraged to name its nodes by label so it can reference them
        without knowing the integer ids the orchestrator will hand out."""
        added: list[str] = []
        src_def = registry.get(self.g.nodes[src_nid]["skill"])

        # Pass 1: add the new nodes; build a label → assigned-id map.
        label_to_id: dict[str, str] = {}
        pending: list[tuple[str, list[str]]] = []
        for spec in result.successors:
            label = (spec.metadata or {}).get("label")
            new_id = self.add_node(spec.skill, inputs=[],
                                   metadata=spec.metadata)
            added.append(new_id)
            if isinstance(label, str) and label:
                label_to_id[label] = new_id
            pending.append((new_id, list(spec.inputs)))

        # Pass 2: resolve inputs now that every sibling has an id. Translate
        # `n:<label>` to `n:<assigned-id>` if the label matches; pass numeric
        # `n:<i>` references through; pass anything else through unchanged.
        # NOTE: an empty `raw_inputs` is now a legitimate Planner signal for
        # a fan-out worker scoped via `metadata.question` (see planner.md).
        # We do NOT substitute the parent in that case — doing so would dump
        # the parent's full output (which for the Planner contains every
        # sibling's question) back into the worker's INPUTS block and undo
        # the scoping. The structural parent edge is preserved separately
        # below so the graph topology is still correct.
        for new_id, raw_inputs in pending:
            resolved: list[str] = []
            for inp in raw_inputs:
                # `n:<label>` or `n:<int>` form (preferred).
                if inp.startswith("n:"):
                    suffix = inp[2:]
                    if suffix in label_to_id:
                        resolved.append(label_to_id[suffix])
                        continue
                    if suffix.isdigit() and inp in self.g.nodes:
                        resolved.append(inp)
                        continue
                # Bare label form — the Planner sometimes drops the n: prefix.
                if inp in label_to_id:
                    resolved.append(label_to_id[inp])
                    continue
                # Special literal — the user query is always available.
                if inp == "USER_QUERY":
                    resolved.append(inp)
                    continue
                # Artifact handle — pass through, the input renderer handles it.
                if inp.startswith("art:"):
                    resolved.append(inp)
                    continue
                # Unresolvable input — fall back to the parent so the child
                # has at least one upstream dependency to wait on. This still
                # leaks the parent's output into INPUTS, but only when the
                # Planner emitted a bad input name; it is not the fan-out
                # path. A future round may want to fail loudly here instead.
                resolved.append(src_nid)
            self.g.nodes[new_id]["inputs"] = resolved
            for inp in resolved:
                if inp.startswith("n:") and inp in self.g.nodes:
                    self.g.add_edge(inp, new_id)
            # Fan-out worker case: planner emitted inputs=[] on purpose. No
            # data dependency, but we still record the structural parent
            # edge so the executor's `ready_nodes` ordering and replay
            # topology stay coherent.
            if not raw_inputs:
                self.g.add_edge(src_nid, new_id)

        for child_skill in src_def.internal_successors:
            nid = self.add_node(child_skill, inputs=[src_nid])
            added.append(nid)

        # Critic auto-insertion: when a `critic: true` skill completes,
        # gate every outgoing edge (to a non-critic child) with a Critic
        # node. Covers BOTH newly-added dynamic successors AND pre-existing
        # edges from the initial Planner plan — earlier versions only saw
        # `added`, so a pre-planned distiller → formatter chain bypassed
        # the auto-critic entirely (the `critic: true` flag became a no-op
        # in the common pre-planned case). Reading the graph's actual
        # outgoing edges makes the flag load-bearing in both shapes.
        if src_def.critic:
            child_targets: list[str] = []
            for child_nid in list(self.g.successors(src_nid)):
                if self.g.nodes[child_nid].get("skill") == "critic":
                    continue  # already gated
                child_targets.append(child_nid)
            for child_nid in child_targets:
                self.g.remove_edge(src_nid, child_nid)
                # Critics need USER_QUERY: without it the critic falls back
                # to MEMORY HITS for context (and stale hits from prior
                # sessions can fool the critic into believing the user
                # asked a completely different question). With USER_QUERY
                # the critic evaluates against the real ask and not against
                # whatever happens to be top-of-FAISS.
                critic_nid = self.add_node(
                    "critic", inputs=["USER_QUERY", src_nid],
                    metadata={"target": src_nid, "child": child_nid},
                )
                self.g.add_edge(critic_nid, child_nid)
                added.append(critic_nid)

        return added


# ── Executor ─────────────────────────────────────────────────────────────────

class Executor:
    def __init__(self, registry: SkillRegistry | None = None):
        ensure_gateway()
        self.registry = registry or SkillRegistry()

    async def run(self, query: str, *, session_id: str | None = None,
                  resume: bool = False, tracer: Session8Tracer | None = None) -> str:
        sid = session_id or f"s8-{uuid.uuid4().hex[:8]}"
        store = SessionStore(sid)

        # Create tracer if not provided
        if tracer is None:
            log_dir = Path(__file__).parent / "logs"
            log_dir.mkdir(exist_ok=True)
            log_filename = f"session_{sid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            log_file = log_dir / log_filename
            tracer = Session8Tracer(enabled=True, log_file=log_file, session_id=sid, query=query)

        if resume:
            existing = store.read_graph()
            if existing is None:
                raise RuntimeError(f"cannot resume {sid}: no graph.pkl on disk")
            graph_obj = existing
            graph = Graph.__new__(Graph)
            graph.g = graph_obj
            graph._counter = max(
                [int(n.split(":")[1]) for n in graph.g.nodes if n.startswith("n:")] or [0]
            )
            for _, d in graph.g.nodes(data=True):
                if d["status"] == "running":
                    d["status"] = "pending"
            if not query:
                query = store.read_query()
        else:
            store.write_query(query)
            graph = Graph()
            graph.add_node("planner", inputs=["USER_QUERY"])

        # Log session start with memory hits
        memory_hits = memory_svc.read(query) or []
        tracer.session_start(sid, query, len(memory_hits))

        # Log detailed memory hits
        if memory_hits:
            tracer.memory_hits_detail(memory_hits)

        try:
            memory_svc.remember(query, source="user_query", run_id=sid)
        except Exception as e:
            tracer.custom("memory.remember", f"skipped: {e!r}")

        formatter_answer: str | None = None
        executed_count = 0
        # Per-target cap for critic-fail recovery; see P1 #5 fix below.
        recovered_branches: dict[str, bool] = {}
        # NOTES_RUNS round-3 review #5: when the cap fires, the branch is
        # skipped silently and the final answer reflects missing data with
        # no flag. Track every second-or-later critic-fail here so the
        # final log can surface it.
        critic_fail_cap_hit: list[str] = []

        while True:
            ready = graph.ready_nodes()
            if not ready and not graph.has_running():
                break
            if executed_count + len(ready) > MAX_NODES:
                print(f"[flow] node cap {MAX_NODES} hit at {executed_count}; stopping")
                break

            for nid in ready:
                graph.mark(nid, "running")
            store.write_graph(graph.g)

            outcomes = await asyncio.gather(*[self._run_one(nid, graph, sid, query, store, memory_hits, tracer)
                                              for nid in ready])

            for nid, result, prompt in outcomes:
                executed_count += 1
                graph.g.nodes[nid]["result"] = result
                graph.mark(nid, "complete" if result.success else "failed")
                store.write_node(NodeState(
                    node_id=nid, skill=graph.g.nodes[nid]["skill"],
                    status=graph.g.nodes[nid]["status"],
                    inputs=graph.g.nodes[nid]["inputs"],
                    result=result, prompt_sent=prompt,
                    started_at=time.time() - result.elapsed_s,
                    completed_at=time.time(),
                ))

                # Log node completion with tracer
                tracer.node_complete(
                    nid,
                    graph.g.nodes[nid]["skill"],
                    graph.g.nodes[nid]["status"],
                    result.error
                )

                if result.success:
                    if graph.g.nodes[nid]["skill"] == "critic":
                        if handle_critic_verdict(nid, result, graph,
                                                 recovered_branches,
                                                 critic_fail_cap_hit):
                            continue
                        # verdict == pass: the child is now ready to run.

                    # Extend graph with successors and log them
                    added_nodes = graph.extend_from(nid, result, registry=self.registry)
                    if added_nodes:
                        tracer.node_successors(nid, added_nodes)

                    if graph.g.nodes[nid]["skill"] == "formatter":
                        fa = result.output.get("final_answer")
                        if isinstance(fa, str) and fa.strip():
                            formatter_answer = fa
                else:
                    failed_skill = graph.g.nodes[nid]["skill"]
                    decision = plan_recovery(
                        failed_skill=failed_skill,
                        error_text=result.error or "",
                        failed_node_id=nid,
                    )
                    if decision.action == "skip":
                        tracer.custom("recovery", f"{nid} skipped ({decision.reason}): {decision.note}")
                        continue
                    # action == "replan"
                    rec_nid = graph.add_node(
                        "planner", inputs=["USER_QUERY"],
                        metadata={"failure_report": decision.failure_report,
                                  "recovers": nid,
                                  "recovery_reason": decision.reason},
                    )
                    tracer.custom("recovery", f"planner {rec_nid} queued for {nid} ({decision.reason})")
                    tracer.node_successors(nid, [rec_nid])

            store.write_graph(graph.g)

        if formatter_answer is None:
            for nid in reversed(list(graph.g.nodes)):
                d = graph.g.nodes[nid]
                if d["status"] == "complete" and isinstance(d.get("result"), AgentResult):
                    formatter_answer = json.dumps(d["result"].output)[:2000]
                    break

        if critic_fail_cap_hit:
            # Loud surface — see review round-3 #5. Without this the cap
            # firing was invisible and the user would just see a thin
            # formatter answer with no explanation of why.
            warning_msg = (f"critic-fail cap hit on {len(critic_fail_cap_hit)} branch(es): "
                          f"{', '.join(critic_fail_cap_hit)}")
            tracer.custom("flow", f"WARNING: {warning_msg}")

        # Log final answer
        tracer.final_answer(formatter_answer or "")
        tracer.finalize()

        # Print execution statistics
        from session_stats import print_session_stats
        print_session_stats(sid, store)

        return formatter_answer or ""

    async def _run_one(self, nid: str, graph: Graph, sid: str, query: str,
                       store: SessionStore, memory_hits: list,
                       tracer: Session8Tracer) -> tuple[str, AgentResult, str]:
        skill_name = graph.g.nodes[nid]["skill"]
        skill = self.registry.get(skill_name)
        fr = graph.g.nodes[nid].get("metadata", {}).get("failure_report")

        # Log node start
        tracer.node_start(nid, skill_name, graph.g.nodes[nid]["inputs"])

        store.write_node(NodeState(node_id=nid, skill=skill_name, status="running",
                                   inputs=graph.g.nodes[nid]["inputs"],
                                   started_at=time.time()))
        try:
            result, prompt = await run_skill(skill, nid, graph.g.nodes, sid, query, fr,
                                             memory_hits=memory_hits, tracer=tracer)
        except Exception as e:  # pragma: no cover - dispatcher fault path
            result = AgentResult(success=False, agent_name=skill_name,
                                 error=f"exception: {type(e).__name__}: {e}")
            prompt = "(exception before prompt-render)"
        return nid, result, prompt


# ── CLI ──────────────────────────────────────────────────────────────────────

async def interactive_loop() -> None:
    """
    Run the Session 8 agent in interactive mode with continuous prompt loop.
    Each query creates a new session. Sessions are saved and can be resumed later.
    """
    from datetime import datetime
    from pathlib import Path

    # Create logs directory if it doesn't exist
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)

    # Create log file with timestamp
    log_filename = f"session8_interactive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_file = log_dir / log_filename

    print("=" * 80)
    print("SESSION 8 AGENT - Interactive Mode")
    print("=" * 80)
    print("Type your query and press Enter to run the agent.")
    print("Type 'exit', 'quit', or press Ctrl+C to stop.")
    print(f"[LOG] Session logs saved to: {log_file}")
    print("=" * 80)
    print()

    executor = Executor()

    with open(log_file, 'w', encoding='utf-8') as f:
        f.write(f"Session 8 Interactive Log - {datetime.now()}\n")
        f.write("=" * 80 + "\n\n")

    while True:
        try:
            # Get user input
            user_query = input("You: ").strip()

            # Check for exit commands
            if user_query.lower() in ["exit", "quit"]:
                print("\nGoodbye!")
                break

            # Skip empty queries
            if not user_query:
                continue

            print()  # Add spacing before agent output

            # Generate session ID for this query
            sid = f"s8-{uuid.uuid4().hex[:8]}"

            # Log the query
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"\n{'-' * 80}\n")
                f.write(f"Session: {sid}\n")
                f.write(f"Time: {datetime.now()}\n")
                f.write(f"Query: {user_query}\n")
                f.write(f"{'-' * 80}\n\n")

            # Run the agent
            result = await executor.run(user_query, session_id=sid)

            # Log the result
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"Result: {result}\n")
                f.write(f"Session saved to: state/sessions/{sid}/\n\n")

            print()  # Add spacing after agent output
            print("─" * 80)
            print()

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\n[ERROR] Error: {e}")
            import traceback
            traceback.print_exc()

            # Log the error
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"ERROR: {e}\n")
                f.write(traceback.format_exc())
                f.write("\n")

            print("-" * 80)
            print()


def main() -> None:
    args = sys.argv[1:]

    # Check for interactive mode flag
    if args and args[0] == "--interactive":
        asyncio.run(interactive_loop())
        return

    # Check for resume mode
    resume_sid: str | None = None
    if args and args[0] == "--resume":
        resume_sid = args[1] if len(args) > 1 else None
        query = " ".join(args[2:])
    else:
        query = " ".join(args) or "Say hello in one short sentence."

    asyncio.run(Executor().run(query, session_id=resume_sid, resume=bool(resume_sid)))


if __name__ == "__main__":
    main()
