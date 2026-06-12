"""Test the Session8Tracer module.

This script tests the tracer functionality including:
- Session start logging
- Memory hits logging
- Node execution logging (start/complete with wall clock time)
- Tool call and result logging
- Final answer logging

Usage:
    python test_tracer.py
"""

from pathlib import Path
from tracer import Session8Tracer
import time


def test_tracer_basic():
    """Test basic tracer functionality."""
    
    print("=" * 80)
    print("Testing Session8Tracer - Basic Functionality")
    print("=" * 80)
    print()
    
    # Create a tracer (console output only, no file)
    tracer = Session8Tracer(enabled=True, session_id="test-123", query="What is 2+2?")
    
    # 1. Session start with memory hits
    print("[Test 1] Session start with memory hits")
    tracer.session_start("test-123", "What is 2+2?", memory_hits=3)
    tracer.separator()
    
    # 2. Memory hits detail
    print("[Test 2] Memory hits detail")
    class MockHit:
        def __init__(self, descriptor):
            self.descriptor = descriptor
    
    hits = [
        MockHit("Previous calculation: 1+1=2"),
        MockHit("Math fact: Addition is commutative"),
        MockHit("User prefers detailed explanations"),
    ]
    tracer.memory_hits_detail(hits)
    tracer.separator()
    
    # 3. Node start
    print("[Test 3] Node execution start")
    tracer.node_start("n:1", "planner", ["USER_QUERY"])
    time.sleep(0.5)  # Simulate some work
    
    # 4. Node complete
    print("[Test 4] Node execution complete")
    tracer.node_complete("n:1", "planner", "complete")
    tracer.separator()
    
    # 5. Node with tools and successors
    print("[Test 5] Node with tool calls and successors")
    tracer.node_start("n:2", "researcher", ["n:1"])

    # Tool call 1
    tracer.tool_call("n:2", "web_search", {"query": "mathematics addition", "num_results": 5})
    time.sleep(0.3)
    tracer.tool_result("n:2", "Found 5 results about addition in mathematics")

    # Tool call 2
    tracer.tool_call("n:2", "fetch_url", {"url": "https://example.com/math"})
    time.sleep(0.2)
    tracer.tool_result("n:2", "Successfully fetched page content: Addition is a basic arithmetic operation...")

    time.sleep(0.5)
    tracer.node_complete("n:2", "researcher", "complete")

    # Log successors emitted by this node
    tracer.node_successors("n:2", ["n:3", "n:4"])
    tracer.separator()
    
    # 6. Failed node with recovery
    print("[Test 6] Node failure with recovery")
    tracer.node_start("n:5", "coder", ["n:2"])
    time.sleep(0.3)
    tracer.node_complete("n:5", "coder", "failed", error="SyntaxError: invalid syntax on line 42")
    tracer.custom("recovery", "planner n:6 queued for n:5 (code_error)")
    tracer.node_successors("n:5", ["n:6"])
    tracer.separator()
    
    # 7. Graph status
    print("[Test 7] Graph status")
    tracer.graph_status(total_nodes=5, completed=3, running=1, pending=1)
    tracer.separator()
    
    # 8. Final answer
    print("[Test 8] Final answer")
    tracer.final_answer("The answer to 2+2 is 4. This is because addition combines two quantities.")
    
    # 9. Custom message
    print("[Test 9] Custom message")
    tracer.custom("system", "Test completed successfully")
    
    print()
    print("=" * 80)
    print("All tracer tests passed!")
    print("=" * 80)


def test_tracer_with_file():
    """Test tracer with file logging."""
    
    print("\n")
    print("=" * 80)
    print("Testing Session8Tracer - File Logging")
    print("=" * 80)
    print()
    
    # Create log directory
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "test_tracer_output.log"
    
    # Remove old log file if exists
    if log_file.exists():
        log_file.unlink()
    
    # Create tracer with file logging
    tracer = Session8Tracer(
        enabled=True,
        log_file=log_file,
        session_id="test-file-456",
        query="Test query for file logging"
    )
    
    tracer.session_start("test-file-456", "Test query for file logging", memory_hits=2)
    tracer.node_start("n:1", "planner", ["USER_QUERY"])
    time.sleep(0.2)
    tracer.node_complete("n:1", "planner", "complete")
    tracer.final_answer("Test answer")
    tracer.finalize()
    
    # Check file was created
    if log_file.exists():
        print(f"[OK] Log file created: {log_file}")
        print(f"[OK] Log file size: {log_file.stat().st_size} bytes")
        print(f"\nFirst 500 characters of log file:")
        print("-" * 80)
        print(log_file.read_text(encoding='utf-8')[:500])
        print("-" * 80)
    else:
        print("[ERROR] Log file was not created!")

    print()
    print("=" * 80)
    print("File logging test complete!")
    print("=" * 80)


if __name__ == "__main__":
    test_tracer_basic()
    test_tracer_with_file()
