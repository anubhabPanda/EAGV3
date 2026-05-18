"""Run the Gemini Agent FastAPI server with MCP via SSE."""
import os
import sys
import uvicorn
from dotenv import load_dotenv

# Fix Windows console encoding
if sys.platform == "win32":
    os.system("chcp 65001 > nul")

# Load environment variables
load_dotenv()

# Add Session 4 to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    mcp_server_url = os.getenv("MCP_SERVER_URL", "http://localhost:8001/sse")

    print("=" * 60)
    print("Starting Gemini Agent API Server (MCP via SSE)")
    print("=" * 60)
    print(f"Agent API: http://localhost:{port}")
    print(f"Docs: http://localhost:{port}/docs")
    print(f"Model: gemini-3.1-flash-lite-preview")
    print(f"MCP Server: {mcp_server_url}")
    print(f"Transport: SSE (Server-Sent Events)")
    print("=" * 60)
    print("\nIMPORTANT:")
    print("   Make sure MCP server is running first!")
    print(f"   Run: python run_dev_server.py")
    print(f"   Or:  python run_mcp_server.py")
    print("=" * 60)
    print("\nAvailable endpoints:")
    print(f"  GET  http://localhost:{port}/")
    print(f"  POST http://localhost:{port}/chat")
    print(f"  POST http://localhost:{port}/reset")
    print(f"  GET  http://localhost:{port}/tools")
    print("\nPress Ctrl+C to stop")
    print("=" * 60)

    uvicorn.run(
        "gemini_agent.api_server:app",
        host="0.0.0.0",
        port=port,
        reload=True
    )
