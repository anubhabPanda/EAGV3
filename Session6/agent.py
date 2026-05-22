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

async def run(query: str) -> str:
    ensure_llm_gateway()
    run_id = uuid.uuid4().hex[:8]
    history: list[dict] = []
    prior_goals: list[Goal] = []

    memory.remember(query, source="user_query", run_id=run_id)

    async with mcp_session() as session:
        mcp_tools = await load_tools(session)
        tools = mcp_tools_for_decision(mcp_tools)

        print("Tools available to the decision layer:", [tool.get("name", "<Unnamed Tool>") for tool in tools])
        
        for it in range(1, MAX_ITERATIONS + 1):
            hits = memory.read(query, history)
            obs = perception.observe(query, hits, history, prior_goals, run_id)
            print(f"\nHits: {hits}")
            print(f"Observation: {obs.model_dump()}")

            # Check if all goals are done - if so, break the loop
            if obs.goals and all(goal.done for goal in obs.goals):
                print(f"\n✓ All {len(obs.goals)} goals completed. Exiting loop.")
                break

            goal = obs.next_unfinished
            print(f"\n\nIteration {it}: Next goal - {goal.text if goal else 'None'}")

            attached = []
            if goal.attach_artifact_id and artifacts.exists(goal.attach_artifact_id):
                attached.append((
                    goal.attach_artifact_id,
                    artifacts.get_bytes(goal.attach_artifact_id),
                ))

            out = decision.next_step(goal, hits, attached, history, tools)

            print(f"\nDecision output: {out.model_dump()}")
            if out.answer:
                history.append({"iter": it, "kind": "answer",
                                "goal_id": goal.id, "text": out.answer})
                continue  
            result_text, art_id = await action.execute(session, out.tool_call)  

            print(f"\nAction result: {result_text[:300]}{'... (truncated)' if len(result_text) > 300 else ''}")
            print(f"Artifact created: {art_id}" if art_id else "No artifact created.")
            memory.record_outcome(
                tool_call=out.tool_call,
                result_text=result_text,
                artifact_id=art_id,
                run_id=run_id,
                goal_id=goal.id,
            )
            history.append({"iter": it, "kind": "action",
                            "goal_id": goal.id, "tool": out.tool_call.name,
                            "arguments": out.tool_call.arguments,
                            "result_descriptor": result_text[:300],
                            "artifact_id": art_id})
            
    return get_final_answer(history)           

if __name__ == "__main__":
    MAX_ITERATIONS = 2
    memory = Memory()
    perception = Perception()
    artifacts = ArtifactStore()
    decision = Decision()
    action = Action()
    asyncio.run(run("My mom's birthday is 15 May 2026. Remember that and give me a calendar reminder for two weeks before and on the day."))