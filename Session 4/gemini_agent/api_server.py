"""FastAPI server for Gemini Agent with MCP integration via SSE."""
import os
import asyncio
from typing import Dict, Any, Optional
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn
import httpx
from dotenv import load_dotenv

# MCP client imports
from mcp import ClientSession
from mcp.client.sse import sse_client

from .agent import GeminiAgent

# Load environment
load_dotenv()


app = FastAPI(title="Gemini Agent API", version="1.0.0")

# Mount static files
static_path = Path(__file__).parent.parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global agent instance
agent: Optional[GeminiAgent] = None
mcp_session: Optional[ClientSession] = None
sse_context = None


class ChatRequest(BaseModel):
    message: str
    max_iterations: int = 15


class ChatResponse(BaseModel):
    text: str
    tool_calls: list = []
    iterations: int = 1
    error: Optional[str] = None
    dashboard_html: Optional[str] = None


class ToolListResponse(BaseModel):
    tools: list


@app.on_event("startup")
async def startup_event():
    """Initialize MCP client and agent on startup."""
    global agent, mcp_session, sse_context

    try:
        # Get MCP server URL from environment
        mcp_server_url = os.getenv("MCP_SERVER_URL", "http://localhost:8001/sse")

        print(f"Connecting to MCP server at {mcp_server_url}...")

        # Add small delay to ensure MCP server is ready
        import asyncio
        await asyncio.sleep(1)

        # Create SSE client using context manager
        print("[DEBUG] Step 1: Creating SSE client...")
        sse_context = sse_client(mcp_server_url)

        print("[DEBUG] Step 2: Entering SSE context...")
        read, write = await sse_context.__aenter__()
        print("[DEBUG] Step 2: SSE context entered successfully")

        # Create session
        print("[DEBUG] Step 3: Creating MCP ClientSession...")
        mcp_session = ClientSession(read, write)

        # Initialize session
        print("[DEBUG] Step 4: Entering session context...")
        await mcp_session.__aenter__()

        print("[DEBUG] Step 5: Initializing session...")
        await mcp_session.initialize()
        print("[DEBUG] Step 5: Session initialized successfully")

        # Create agent with MCP session
        print("[DEBUG] Step 6: Creating GeminiAgent...")
        agent = GeminiAgent(mcp_client=mcp_session)

        print("[OK] Gemini Agent initialized with MCP tools via SSE")
        print(f"   Connected to: {mcp_server_url}")

        # Try to list tools to verify connection
        try:
            tools = await agent.get_available_tools()
            print(f"   Available tools: {len(tools)}")
            for tool in tools:
                print(f"     - {tool.get('name', 'unknown')}")
        except Exception as e:
            print(f"   [WARNING] Could not list tools: {e}")

    except Exception as e:
        print(f"[WARNING] Failed to initialize MCP client: {e}")
        print(f"   Make sure MCP server is running at {os.getenv('MCP_SERVER_URL', 'http://localhost:8001/sse')}")
        print("   Start it with: python run_mcp_server.py")
        print("\n[DEBUG] Full error traceback:")
        import traceback
        traceback.print_exc()
        print("\nStarting agent without MCP tools")
        agent = GeminiAgent(mcp_client=None)


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    global mcp_session, sse_context

    if mcp_session:
        try:
            await mcp_session.__aexit__(None, None, None)
        except:
            pass

    if sse_context:
        try:
            await sse_context.__aexit__(None, None, None)
        except:
            pass


@app.get("/")
async def root():
    """Serve the UI."""
    index_path = Path(__file__).parent.parent / "static" / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {
        "status": "running",
        "service": "Gemini Agent API",
        "mcp_connected": mcp_session is not None
    }


@app.get("/api/status")
async def api_status():
    """API status endpoint."""
    return {
        "status": "running",
        "service": "Gemini Agent API",
        "mcp_connected": mcp_session is not None,
        "agent_ready": agent is not None
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Send a message to the Gemini agent.

    Args:
        request: Chat request with message and optional max_iterations

    Returns:
        Agent response with text and tool call information
    """
    print(f"\n[API] ========== NEW CHAT REQUEST ==========")
    print(f"[API] Message: {request.message[:100]}...")
    print(f"[API] Max iterations: {request.max_iterations}")

    if not agent:
        print(f"[API] ERROR: Agent not initialized")
        raise HTTPException(status_code=503, detail="Agent not initialized")

    try:
        print(f"[API] Calling agent.chat()...")
        response = await agent.chat(request.message, request.max_iterations)

        print(f"[API] Response received:")
        print(f"[API]   - Text length: {len(response.get('text', ''))}")
        print(f"[API]   - Tool calls: {len(response.get('tool_calls', []))}")
        print(f"[API]   - Iterations: {response.get('iterations', 0)}")
        if 'error' in response:
            print(f"[API]   - Error: {response['error']}")

        # Check if dashboard was called and render it
        dashboard_html = None
        if response.get('tool_calls'):
            for tool_call in response['tool_calls']:
                if tool_call.get('tool') == 'dashboard' and tool_call.get('result'):
                    result = tool_call['result']
                    # Check if it's a PrefabApp structure
                    if isinstance(result, dict) and 'view' in result:
                        try:
                            from prefab_ui import PrefabApp
                            # Render the PrefabApp to HTML
                            dashboard_html = PrefabApp(**result).html()
                            print(f"[API] Dashboard HTML generated: {len(dashboard_html)} chars")
                        except Exception as e:
                            print(f"[API] Failed to render dashboard: {e}")

        response['dashboard_html'] = dashboard_html
        return ChatResponse(**response)
    except Exception as e:
        print(f"[API] ERROR in chat endpoint: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")


@app.post("/reset")
async def reset_conversation():
    """Reset the conversation history."""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    agent.reset_conversation()
    return {"status": "success", "message": "Conversation reset"}


@app.get("/tools", response_model=ToolListResponse)
async def list_tools():
    """Get list of available MCP tools."""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    try:
        tools = await agent.get_available_tools()
        return ToolListResponse(tools=tools)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list tools: {str(e)}")


@app.get("/system-instruction")
async def get_system_instruction():
    """Get the current system instruction."""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    instruction = agent.get_system_instruction()
    return {
        "system_instruction": instruction,
        "length": len(instruction) if instruction else 0
    }


@app.post("/system-instruction")
async def set_system_instruction(request: dict):
    """Set a custom system instruction."""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    instruction = request.get("instruction")
    if not instruction:
        raise HTTPException(status_code=400, detail="instruction field is required")

    agent.set_system_instruction(instruction)
    return {
        "status": "success",
        "message": "System instruction updated",
        "length": len(instruction)
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
