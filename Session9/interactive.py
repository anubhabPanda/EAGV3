"""Session 9 Interactive Mode - Continuous query loop with session management.

This script runs the Session 9 agent in interactive mode where you can:
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
Logs are saved to: logs/session9_interactive_<timestamp>.log
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding for emoji support
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        # Python < 3.7 fallback
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, errors='replace')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, errors='replace')

# Ensure we can import from the Session9 directory
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from flow import Executor
from gateway import ensure_gateway
from persistence import SessionStore


async def interactive_loop(resume_session_id: str | None = None) -> None:
    """Run the Session 9 agent in interactive mode."""

    # Create logs directory
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)

    # Create log file with timestamp
    log_filename = f"session9_interactive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_file = log_dir / log_filename

    # Ensure gateway is running
    print("[*] Initializing Session 9 agent...")
    ensure_gateway()

    print("\n" + "=" * 80)
    print("SESSION 9 AGENT - Interactive Mode")
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
        f.write(f"Session 9 Interactive Log - {datetime.now()}\n")
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

        try:
            print(f"[{query_count}] Resuming session {resume_session_id}...")
            answer = await executor.run("", session_id=resume_session_id, resume=True)

            print()
            print(f"[{query_count}] DONE")
            print()

            # Log completion
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"Completed at: {datetime.now()}\n")
                f.write(f"Answer: {answer[:500]}...\n\n")

        except Exception as e:
            print(f"\n[ERROR] {e}")
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"Error: {e}\n\n")

    # Main interactive loop
    try:
        while True:
            print()
            query = input("Query: ").strip()
            print()

            if query.lower() in ('exit', 'quit', 'q'):
                print("[*] Exiting...")
                break

            if not query:
                continue

            query_count += 1
            session_id = f"s9-interactive-{uuid.uuid4().hex[:8]}"

            # Log the query
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"\n{'─' * 80}\n")
                f.write(f"Query #{query_count}\n")
                f.write(f"Session: {session_id}\n")
                f.write(f"Time: {datetime.now()}\n")
                f.write(f"Query: {query}\n")

                f.write(f"{'─' * 80}\n\n")

            try:
                print(f"[{query_count}] Running...")
                answer = await executor.run(query, session_id=session_id)

                print()
                print(f"[{query_count}] DONE")

                # Log completion
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"Completed at: {datetime.now()}\n")
                    f.write(f"Answer: {answer[:500]}...\n\n")

            except KeyboardInterrupt:
                print("\n[*] Interrupted. You can resume this session later with:")
                print(f"    python interactive.py --resume {session_id}")
                raise
            except Exception as e:
                print(f"\n[ERROR] {e}")
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"Error: {e}\n\n")
                print("[*] Continuing to next query...")

    except KeyboardInterrupt:
        print("\n[*] Exiting...")

    print()
    print("=" * 80)
    print(f"Total queries: {query_count}")
    print(f"Log saved to: {log_file}")
    print("=" * 80)


def main():
    """Entry point for interactive mode."""
    import sys

    resume_sid = None
    if len(sys.argv) > 1:
        if sys.argv[1] == "--resume" and len(sys.argv) > 2:
            resume_sid = sys.argv[2]
        else:
            print("Usage: python interactive.py [--resume <session_id>]")
            sys.exit(1)

    asyncio.run(interactive_loop(resume_sid))


if __name__ == "__main__":
    main()
