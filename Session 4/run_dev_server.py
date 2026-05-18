"""Run the FastMCP dev server for Prefab app preview."""
import subprocess
import sys
import os
import shutil

if __name__ == "__main__":
    print("=" * 60)
    print("Starting FastMCP Dev Server for Prefab Apps")
    print("=" * 60)
    print("This starts a dev UI that can properly render Prefab apps")
    print("\nDev UI: http://localhost:8080")
    print("MCP Server: http://localhost:8001")
    print("\nThe dev server provides:")
    print("  - Tool picker at http://localhost:8080")
    print("  - Rendered dashboard at http://localhost:8080/launch?tool=dashboard")
    print("\nPress Ctrl+C to stop")
    print("=" * 60)
    print()

    # Change to mcp_server directory
    mcp_server_dir = os.path.join(os.path.dirname(__file__), "mcp_server")

    # Check if fastmcp command is available
    fastmcp_cmd = shutil.which("fastmcp")
    if not fastmcp_cmd:
        print("ERROR: 'fastmcp' command not found!")
        print("\nPlease install fastmcp with apps support:")
        print("  pip install 'fastmcp[apps]'")
        print("\nThen try again.")
        sys.exit(1)

    # Run fastmcp dev apps
    try:
        subprocess.run(
            [
                "fastmcp", "dev", "apps",
                "server.py",
                "--mcp-port", "8002",
                "--dev-port", "8080"
            ],
            cwd=mcp_server_dir,
            check=True
        )
    except KeyboardInterrupt:
        print("\n\nShutting down dev server...")
    except subprocess.CalledProcessError as e:
        print(f"\nError running dev server: {e}")
        print("\nMake sure:")
        print("  1. fastmcp[apps] is installed: pip install 'fastmcp[apps]'")
        print("  2. The server.py file exists in mcp_server/")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        print("\nMake sure fastmcp[apps] is installed:")
        print("  pip install 'fastmcp[apps]'")
