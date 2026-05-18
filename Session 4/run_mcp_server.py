"""Run the FastMCP server with SSE transport."""
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add Session 4 to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp_server.server import mcp

if __name__ == "__main__":
    port = int(os.getenv("MCP_SERVER_PORT", "8001"))

    print("=" * 60)
    print("Starting FastMCP Server with SSE Transport")
    print("=" * 60)
    print(f"Server URL: http://localhost:{port}")
    print(f"SSE Endpoint: http://localhost:{port}/sse")
    print(f"Transport: SSE (Server-Sent Events)")
    print("\nAvailable tools:")
    print("  - search_web: Search the web")
    print("  - read_file: Read local files")
    print("  - write_file: Write local files")
    print("  - get_weather_info: Get weather information")
    print("  - get_satellite_map: Get satellite images")
    print("  - dashboard: Interactive Prefab UI dashboard")
    print("\nPress Ctrl+C to stop")
    print("=" * 60)

    # Run with SSE transport using http_app for better control
    import uvicorn
    app = mcp.http_app(transport="sse")
    uvicorn.run(app, host="0.0.0.0", port=port)
