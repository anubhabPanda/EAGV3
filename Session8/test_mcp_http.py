"""Test the MCP server HTTP transport.

This script tests that the MCP server can be accessed via HTTP and that
tools can be called successfully.

Usage:
    1. Start the MCP server: python mcp_server.py
    2. Run this test: python test_mcp_http.py
"""

import asyncio
import sys
from pathlib import Path

# Ensure we can import from Session8
sys.path.insert(0, str(Path(__file__).parent))

from mcp.client.streamable_http import streamable_http_client
from mcp import ClientSession


async def test_mcp_http():
    """Test MCP server via HTTP transport."""
    
    url = "http://127.0.0.1:8008/mcp"
    
    print("=" * 80)
    print("Testing MCP Server HTTP Transport")
    print("=" * 80)
    print(f"Connecting to: {url}")
    print()
    
    try:
        async with streamable_http_client(url) as (read, write, _):
            async with ClientSession(read, write) as session:
                # Initialize session
                print("[1/4] Initializing session...")
                await session.initialize()
                print("      OK - Session initialized")
                print()
                
                # List available tools
                print("[2/4] Listing tools...")
                tools_result = await session.list_tools()
                tools = [t.name for t in tools_result.tools]
                print(f"      OK - Found {len(tools)} tools:")
                for tool in tools:
                    print(f"        - {tool}")
                print()
                
                # Test get_time tool
                print("[3/4] Testing get_time tool...")
                result = await session.call_tool("get_time", arguments={"timezone": "UTC"})
                content = result.content[0].text if result.content else "No content"
                print(f"      OK - Result: {content[:100]}...")
                print()
                
                # Test currency_convert tool
                print("[4/4] Testing currency_convert tool...")
                result = await session.call_tool(
                    "currency_convert",
                    arguments={"amount": 100, "from_currency": "USD", "to_currency": "EUR"}
                )
                content = result.content[0].text if result.content else "No content"
                print(f"      OK - Result: {content[:100]}...")
                print()
                
        print("=" * 80)
        print("All tests passed!")
        print("=" * 80)
        return True
        
    except ConnectionRefusedError:
        print("\n[ERROR] Connection refused!")
        print("Make sure the MCP server is running:")
        print("  cd Session8")
        print("  python mcp_server.py")
        print()
        return False
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_with_mcp_runner():
    """Test using the mcp_runner module (as the agent uses it)."""
    
    print("\n" + "=" * 80)
    print("Testing via mcp_runner module")
    print("=" * 80)
    print()
    
    try:
        from mcp_runner import _mcp_session
        
        print("[1/2] Connecting via _mcp_session()...")
        async with _mcp_session() as session:
            print("      OK - Connected")
            print()
            
            print("[2/2] Listing tools...")
            tools_result = await session.list_tools()
            tools = [t.name for t in tools_result.tools]
            print(f"      OK - Found {len(tools)} tools via mcp_runner")
            print()
            
        print("=" * 80)
        print("mcp_runner test passed!")
        print("=" * 80)
        return True
        
    except Exception as e:
        print(f"\n[ERROR] mcp_runner test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Test direct HTTP connection
    success1 = asyncio.run(test_mcp_http())
    
    # Test via mcp_runner (as agent uses it)
    success2 = asyncio.run(test_with_mcp_runner())
    
    if success1 and success2:
        print("\n✓ All MCP HTTP transport tests passed!")
        sys.exit(0)
    else:
        print("\n✗ Some tests failed")
        sys.exit(1)
