from __future__ import annotations
import sys
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from persistence import SessionStore


def print_session_stats(session_id: str, store: SessionStore) -> None:
    states = store.read_all_nodes()
    
    timed_nodes = [
        st for st in states
        if st.started_at is not None 
        and st.completed_at is not None
        and st.result is not None
    ]
    
    if not timed_nodes:
        print("\n[stats] No timing data available")
        return
    
    timed_nodes.sort(key=lambda st: int(st.node_id.split(":")[1]))
    session_start = min(st.started_at for st in timed_nodes)
    
    rows = []
    total_elapsed = 0.0
    total_cost = 0.0
    max_finish_rel = 0.0

    for st in timed_nodes:
        start_rel = st.started_at - session_start
        elapsed = st.result.elapsed_s if st.result else 0.0
        finish_rel = start_rel + elapsed
        cost = st.result.cost if st.result else 0.0

        rows.append({
            'node': st.node_id,
            'skill': st.skill,
            'start_rel': start_rel,
            'elapsed': elapsed,
            'finish_rel': finish_rel,
            'cost': cost,
        })

        total_elapsed += elapsed
        total_cost += cost
        max_finish_rel = max(max_finish_rel, finish_rel)
    
    wall_clock = max_finish_rel
    speedup = total_elapsed / wall_clock if wall_clock > 0 else 0.0
    
    print()
    print("=" * 90)
    print(f"Session {session_id} - Execution Statistics")
    print("=" * 90)
    print()
    print(f"{'node':<6} {'skill':<18} {'start (rel)':<12} {'elapsed':<10} {'finish (rel)':<12} {'cost':<10}")
    print("-" * 90)

    for row in rows:
        print(
            f"{row['node']:<6} "
            f"{row['skill']:<18} "
            f"{row['start_rel']:>9.2f} s  "
            f"{row['elapsed']:>7.2f} s  "
            f"{row['finish_rel']:>9.2f} s  "
            f"${row['cost']:>8.5f}"
        )

    print()
    print(f"wall-clock end-to-end:       {wall_clock:>7.2f} s")
    print(f"sum-of-elapsed (serial):    {total_elapsed:>7.2f} s")
    print(f"parallel speedup ratio:       {speedup:>6.2f}x")
    print(f"total cost (USD):              ${total_cost:>6.4f}")
    print("=" * 90)
    print()


def get_session_stats(session_id: str, store: SessionStore) -> dict:
    states = store.read_all_nodes()
    
    timed_nodes = [
        st for st in states
        if st.started_at is not None 
        and st.completed_at is not None
        and st.result is not None
    ]
    
    if not timed_nodes:
        return {
            'nodes': [],
            'wall_clock': 0.0,
            'total_elapsed': 0.0,
            'speedup': 0.0
        }
    
    timed_nodes.sort(key=lambda st: int(st.node_id.split(":")[1]))
    session_start = min(st.started_at for st in timed_nodes)
    
    nodes = []
    total_elapsed = 0.0
    total_cost = 0.0
    max_finish_rel = 0.0

    for st in timed_nodes:
        start_rel = st.started_at - session_start
        elapsed = st.result.elapsed_s if st.result else 0.0
        finish_rel = start_rel + elapsed
        cost = st.result.cost if st.result else 0.0

        nodes.append({
            'node_id': st.node_id,
            'skill': st.skill,
            'start_rel': start_rel,
            'elapsed': elapsed,
            'finish_rel': finish_rel,
            'cost': cost,
        })

        total_elapsed += elapsed
        total_cost += cost
        max_finish_rel = max(max_finish_rel, finish_rel)

    wall_clock = max_finish_rel
    speedup = total_elapsed / wall_clock if wall_clock > 0 else 0.0

    return {
        'nodes': nodes,
        'wall_clock': wall_clock,
        'total_elapsed': total_elapsed,
        'speedup': speedup,
        'total_cost': total_cost
    }
