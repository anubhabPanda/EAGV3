import asyncio
import sys
import os
from pathlib import Path
from contextlib import asynccontextmanager
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from services.decision_service import Decision
from services.memory_service import Memory
from services.perception_service import Perception
from services.artifact_service import ArtifactStore
from services.action_service import Action
from utils import ensure_llm_gateway
from tracer import AgentTracer
import uuid
from schemas import Goal
import threading

# MCP Transport Configuration
MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", "http")  # stdio or http
MCP_HTTP_URL = os.environ.get("MCP_HTTP_URL", "http://127.0.0.1:8000/mcp")


def _stderr_reader(stderr_stream, tracer: AgentTracer):
    """Read MCP server stderr and log to tracer file."""
    try:
        for line in iter(stderr_stream.readline, b''):
            if not line:
                break
            decoded = line.decode('utf-8', errors='replace').rstrip()
            # Write to tracer's log file if available
            if tracer and tracer.log_file:
                try:
                    with open(tracer.log_file, 'a', encoding='utf-8') as f:
                        f.write(decoded + '\n')
                except Exception:
                    pass
            # Also print to terminal stderr
            print(decoded, file=sys.stderr, flush=True)
    except Exception:
        pass


@asynccontextmanager
async def mcp_session(tracer: AgentTracer = None):
    """
    Context manager for MCP server connection.

    Supports two transports:
    - stdio: Local subprocess (default)
    - http: Remote HTTP server

    Set MCP_TRANSPORT=http and MCP_HTTP_URL to use HTTP transport.

    Args:
        tracer: Optional tracer to capture MCP tool logs (stderr)
    """
    if MCP_TRANSPORT == "http":
        # HTTP transport - connect to remote server
        async with streamable_http_client(MCP_HTTP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
    else:
        # stdio transport - launch subprocess
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).with_name("mcp_server.py"))],
        )

        async with stdio_client(server_params) as (read, write):
            # Capture stderr from MCP server process
            if tracer and hasattr(read, '_process'):
                process = read._process
                if process and process.stderr:
                    # Start thread to read stderr and log it
                    stderr_thread = threading.Thread(
                        target=_stderr_reader,
                        args=(process.stderr, tracer),
                        daemon=True
                    )
                    stderr_thread.start()

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

async def run(query: str, tracer: AgentTracer = None, run_id: str = None) -> str:
    ensure_llm_gateway()

    # Generate run_id if not provided
    if run_id is None:
        run_id = uuid.uuid4().hex[:8]

    # Initialize tracer if not provided
    if tracer is None:
        tracer = AgentTracer(enabled=True)

    # Update tracer with run_id and user_prompt if not set
    if not tracer.run_id:
        tracer.run_id = run_id
        tracer.user_prompt = query
        tracer._write_header()

    history: list[dict] = []
    prior_goals: list[Goal] = []

    # Set tracer on memory service
    memory.tracer = tracer

    # Log memory classification (memory.remember now logs via tracer internally)
    memory_item = memory.remember(query, source="user_query", run_id=run_id)

    async with mcp_session(tracer=tracer) as session:
        mcp_tools = await load_tools(session)
        tools = mcp_tools_for_decision(mcp_tools)

        for it in range(1, MAX_ITERATIONS + 1):
            # Start iteration
            tracer.iteration_start(it)

            # Memory read (memory.read now logs via tracer internally, including vector search)
            hits = memory.read(query, history, top_k=3)

            # Perception
            obs = perception.observe(query, hits, history, prior_goals, run_id)
            tracer.perception(obs.goals, obs.next_unfinished)

            # Update prior goals for next iteration
            prior_goals = obs.goals

            # Check if all goals are done and perception provided a final answer
            if obs.goals and all(goal.done for goal in obs.goals):
                if obs.final_answer:
                    tracer.custom("system", f"All {len(obs.goals)} goals completed", indent=True)
                    tracer.final_answer(obs.final_answer)
                    return obs.final_answer
                else:
                    tracer.custom("system", f"All {len(obs.goals)} goals completed but no final answer", indent=True)
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

            # Create descriptor for the result
            # Try to extract meaningful text from JSON responses
            descriptor = result_text
            try:
                import json
                parsed = json.loads(result_text)
                if isinstance(parsed, dict):
                    # Extract text field if available
                    if "text" in parsed:
                        descriptor = parsed["text"]
                    elif "title" in parsed and "snippet" in parsed:
                        descriptor = f"{parsed['title']}: {parsed['snippet']}"
                    elif "content" in parsed:
                        descriptor = parsed["content"]
                    else:
                        descriptor = json.dumps(parsed, indent=2)
                elif isinstance(parsed, list) and len(parsed) > 0:
                    # Show first item
                    first = parsed[0]
                    if isinstance(first, dict) and "title" in first:
                        descriptor = f"{first.get('title', '')}: {first.get('snippet', first.get('url', ''))}"
                    else:
                        descriptor = json.dumps(parsed[:3], indent=2)
            except:
                pass

            # Truncate
            if len(descriptor) > 500:
                descriptor = descriptor[:497] + "..."

            tracer.action_result(
                success=not is_error,
                message=result_text if is_error else "",
                artifact_id=art_id,
                descriptor=descriptor
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

async def interactive_loop():
    """
    Run the agent in interactive mode with continuous prompt loop.
    Logs are displayed in terminal and saved to file.
    """
    from datetime import datetime

    # Create logs directory if it doesn't exist
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)

    # Create log file with timestamp
    log_filename = f"agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_file = log_dir / log_filename

    print("=" * 80)
    print("🤖 Agent Interactive Mode")
    print("=" * 80)
    print("Type your prompt and press Enter to run the agent.")
    print("Type 'exit', 'quit', or press Ctrl+C to stop.")
    print(f"📝 Logs saved to: {log_file}")
    print("=" * 80)
    print()

    while True:
        try:
            # Get user input
            user_prompt = input("👤 You: ").strip()

            # Check for exit commands
            if user_prompt.lower() in ["exit", "quit"]:
                print("\n👋 Goodbye!")
                break

            # Skip empty prompts
            if not user_prompt:
                continue

            print()  # Add spacing before agent output

            # Generate run ID for this session
            run_id = uuid.uuid4().hex[:8]

            # Create tracer with file logging
            tracer = AgentTracer(
                enabled=True,
                log_file=log_file,
                run_id=run_id,
                user_prompt=user_prompt
            )

            # Run the agent with the tracer and run_id
            result = await run(user_prompt, tracer=tracer, run_id=run_id)

            # Finalize the log entry
            tracer.finalize()

            print()  # Add spacing after agent output
            print("-" * 80)
            print()

        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
            print("-" * 80)
            print()


if __name__ == "__main__":
    MAX_ITERATIONS = 10
    memory = Memory()
    perception = Perception()
    artifacts = ArtifactStore()
    decision = Decision()
    action = Action()

    # Run interactive loop
    asyncio.run(interactive_loop())
