#!/usr/bin/env python3
"""Standalone script to view session statistics with cost breakdown.

Usage:
    python view_stats.py                           # shows latest session
    python view_stats.py s9-interactive-870f73ec   # shows specific session
"""

from __future__ import annotations
import sys
from pathlib import Path

# Fix Windows console encoding for emoji support
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, errors='replace')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, errors='replace')

from persistence import SessionStore
from session_stats import print_session_stats


def get_latest_session() -> str | None:
    """Find the most recently modified session directory."""
    sessions_dir = Path(__file__).parent / "state" / "sessions"
    if not sessions_dir.exists():
        return None
    
    session_dirs = [d for d in sessions_dir.iterdir() if d.is_dir() and d.name.startswith("s9-interactive-")]
    if not session_dirs:
        return None
    
    # Sort by modification time
    latest = max(session_dirs, key=lambda d: d.stat().st_mtime)
    return latest.name


def main():
    if len(sys.argv) > 1:
        session_id = sys.argv[1]
    else:
        session_id = get_latest_session()
        if not session_id:
            print("No sessions found in state/sessions/")
            print("\nUsage: python view_stats.py [session_id]")
            sys.exit(1)
        print(f"[info] Using latest session: {session_id}\n")
    
    try:
        store = SessionStore(session_id=session_id)
        print_session_stats(session_id, store)
    except Exception as e:
        print(f"Error loading session {session_id}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
