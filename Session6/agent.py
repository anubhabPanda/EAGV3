import asyncio
import sys
from pathlib import Path
from contextlib import asynccontextmanager
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from services.decision_service import Decision
from services.memory_service import Memory
from services.perception_service import Perception
from services.artifact_service import ArtifactStore
from services.action_service import Action
from utils import ensure_llm_gateway
from tracer import AgentTracer
import uuid
from schemas import Goal


@asynccontextmanager
async def mcp_session():
    """Context manager for MCP server connection."""
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).with_name("mcp_server.py"))],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def load_tools(session: ClientSession) -> list:
    """Load tools from the MCP server."""
    result = await session.list_tools()
    return result.tools


def mcp_tools_for_decision(mcp_tools: list) -> list[dict]:
    """Convert MCP tools to a format suitable for decision making."""
    tools = []
    for tool in mcp_tools:
        tools.append({
            "name": tool.name,
            "description": tool.description or "",
            "input_schema": tool.inputSchema or {"type": "object", "properties": {}},
        })
    return tools

def get_final_answer(history: list[dict]) -> str:
    """Extract the final answer from the history."""
    for entry in reversed(history):
        if entry["kind"] == "answer" and entry.get("text"):
            return "Final Answer: \n" + entry["text"]
    return "No answer found."

async def run(query: str, tracer: AgentTracer = None) -> str:
    ensure_llm_gateway()

    # Initialize tracer if not provided
    if tracer is None:
        tracer = AgentTracer(enabled=True)

    run_id = uuid.uuid4().hex[:8]
    history: list[dict] = []
    prior_goals: list[Goal] = []

    # Log memory classification
    memory_item = memory.remember(query, source="user_query", run_id=run_id)
    tracer.memory_remember(
        raw_text=query,
        kind=memory_item.kind,
        keywords=memory_item.keywords
    )

    async with mcp_session() as session:
        mcp_tools = await load_tools(session)
        tools = mcp_tools_for_decision(mcp_tools)

        for it in range(1, MAX_ITERATIONS + 1):
            # Start iteration
            tracer.iteration_start(it)

            # Perception
            hits = memory.read(query, history)
            obs = perception.observe(query, hits, history, prior_goals, run_id)
            tracer.perception(obs.goals, obs.next_unfinished)

            # Update prior goals for next iteration
            prior_goals = obs.goals

            # Check if all goals are done - if so, break the loop
            if obs.goals and all(goal.done for goal in obs.goals):
                tracer.custom("system", f"All {len(obs.goals)} goals completed", indent=True)
                break

            # Get next unfinished goal
            goal = obs.next_unfinished
            if not goal:
                tracer.custom("system", "No unfinished goals found", indent=True)
                break

            # Attach artifacts if needed
            attached = []
            if goal.attach_artifact_id and artifacts.exists(goal.attach_artifact_id):
                attached.append((
                    goal.attach_artifact_id,
                    artifacts.get_bytes(goal.attach_artifact_id),
                ))

            # Decision
            out = decision.next_step(goal, hits, attached, history, tools)

            if out.answer:
                # Decision returned an answer
                tracer.decision_answer(out.answer)
                history.append({
                    "iter": it,
                    "kind": "answer",
                    "goal_id": goal.id,
                    "text": out.answer
                })

                # Check if this is the final answer
                if it == MAX_ITERATIONS or all(g.done for g in obs.goals):
                    tracer.final_answer(out.answer)
                    return out.answer
                continue

            # Decision returned a tool call
            tracer.decision_tool_call(out.tool_call)

            # Action
            result_text, art_id = await action.execute(session, out.tool_call)

            # Log action result
            is_error = "error" in result_text.lower() or "failed" in result_text.lower()
            tracer.action_result(
                success=not is_error,
                message=result_text if is_error else "",
                artifact_id=art_id
            )

            # Record outcome in memory
            memory.record_outcome(
                tool_call=out.tool_call,
                result_text=result_text,
                artifact_id=art_id,
                run_id=run_id,
                goal_id=goal.id,
            )

            # Add to history
            history.append({
                "iter": it,
                "kind": "action",
                "goal_id": goal.id,
                "tool": out.tool_call.name,
                "arguments": out.tool_call.arguments,
                "result_descriptor": result_text[:300],
                "artifact_id": art_id
            })

    # Get final answer from history
    final = get_final_answer(history)
    tracer.final_answer(final)
    return final

if __name__ == "__main__":
    MAX_ITERATIONS = 5
    memory = Memory()
    perception = Perception()
    artifacts = ArtifactStore()
    decision = Decision()
    action = Action()
    asyncio.run(run("When is mom's birthday?"))