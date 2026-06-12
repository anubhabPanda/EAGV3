"""Session 8 Interactive Mode - Continuous query loop with session management.

This script runs the Session 8 agent in interactive mode where you can:
- Enter queries continuously in a loop
- Each query creates a new session automatically
- All sessions are saved and can be replayed later
- Logs are saved to the logs/ directory
- Resume existing sessions with --resume

Usage:
    python interactive.py
    python interactive.py --resume <session_id>

Commands:
    - Type any query and press Enter to run the agent
    - Type 'exit' or 'quit' to stop
    - Press Ctrl+C to stop

Sessions are saved to: state/sessions/<session_id>/
Logs are saved to: logs/session8_interactive_<timestamp>.log
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Ensure we can import from the Session8 directory
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from flow import Executor
from gateway import ensure_gateway
from persistence import SessionStore


async def interactive_loop(resume_session_id: str | None = None) -> None:
    """Run the Session 8 agent in interactive mode."""

    # Create logs directory
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)

    # Create log file with timestamp
    log_filename = f"session8_interactive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_file = log_dir / log_filename

    # Ensure gateway is running
    print("[*] Initializing Session 8 agent...")
    ensure_gateway()

    print("\n" + "=" * 80)
    print("SESSION 8 AGENT - Interactive Mode")
    print("=" * 80)

    if resume_session_id:
        print(f"[RESUME] Resuming session: {resume_session_id}")
        store = SessionStore(resume_session_id)
        existing_query = store.read_query()
        if existing_query:
            print(f"[RESUME] Original query: {existing_query[:100]}...")
    else:
        print("Type your query and press Enter to run the agent.")

    print("Type 'exit', 'quit', or press Ctrl+C to stop.")
    print()
    print(f"[LOG] Session logs: {log_file}")
    print(f"[SAVE] Sessions saved to: state/sessions/")
    print("=" * 80)
    print()

    executor = Executor()

    # Initialize log file
    with open(log_file, 'w', encoding='utf-8') as f:
        f.write(f"Session 8 Interactive Log - {datetime.now()}\n")
        f.write("=" * 80 + "\n\n")
        if resume_session_id:
            f.write(f"Resuming session: {resume_session_id}\n\n")

    query_count = 0

    # Handle resume mode
    if resume_session_id:
        query_count += 1
        print()

        # Log the resume
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"\n{'─' * 80}\n")
            f.write(f"Query #{query_count} (RESUME)\n")
            f.write(f"Session: {resume_session_id}\n")
            f.write(f"Time: {datetime.now()}\n")
            f.write(f"{'─' * 80}\n\n")

        # Run the agent in resume mode
        try:
            result = await executor.run("", session_id=resume_session_id, resume=True)

            # Log the result
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"Result: {result}\n")
                f.write(f"Session resumed: state/sessions/{resume_session_id}/\n\n")

        except Exception as e:
            print(f"\n[ERROR] Error resuming session: {e}")
            import traceback
            traceback.print_exc()

            # Log the error
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"ERROR: {e}\n")
                f.write(traceback.format_exc())
                f.write("\n")

        print()
        print("─" * 80)
        print()
        print("[RESUME] Session completed. You can continue with new queries or exit.")
        print()

    while True:
        try:
            # Get user input
            user_query = input("You: ").strip()

            # Check for exit commands
            if user_query.lower() in ["exit", "quit"]:
                print("\nGoodbye!")
                print(f"\nSummary: {query_count} queries processed")
                break

            # Skip empty queries
            if not user_query:
                continue

            query_count += 1
            print()  # Add spacing before agent output

            # Generate session ID for this query
            sid = f"s8-{uuid.uuid4().hex[:8]}"

            # Log the query
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"\n{'─' * 80}\n")
                f.write(f"Query #{query_count}\n")
                f.write(f"Session: {sid}\n")
                f.write(f"Time: {datetime.now()}\n")
                f.write(f"Query: {user_query}\n")
                f.write(f"{'─' * 80}\n\n")

            # Run the agent
            try:
                result = await executor.run(user_query, session_id=sid)

                # Log the result
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"Result: {result}\n")
                    f.write(f"Session saved: state/sessions/{sid}/\n\n")

            except Exception as e:
                print(f"\n[ERROR] Error running agent: {e}")
                import traceback
                traceback.print_exc()

                # Log the error
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"ERROR: {e}\n")
                    f.write(traceback.format_exc())
                    f.write("\n")

            print()  # Add spacing after agent output
            print("─" * 80)
            print()

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            print(f"\nSummary: {query_count} queries processed")
            break
        except EOFError:
            print("\n\nGoodbye!")
            print(f"\nSummary: {query_count} queries processed")
            break


if __name__ == "__main__":
    resume_sid = None
    if len(sys.argv) > 1:
        if sys.argv[1] == "--resume" and len(sys.argv) > 2:
            resume_sid = sys.argv[2]
        else:
            print("Usage: python interactive.py [--resume <session_id>]")
            sys.exit(1)

    asyncio.run(interactive_loop(resume_sid))
