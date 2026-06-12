from __future__ import annotations
from typing import TYPE_CHECKING

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
    max_finish_rel = 0.0
    
    for st in timed_nodes:
        start_rel = st.started_at - session_start
        elapsed = st.result.elapsed_s if st.result else 0.0
        finish_rel = start_rel + elapsed
        
        rows.append({
            'node': st.node_id,
            'skill': st.skill,
            'start_rel': start_rel,
            'elapsed': elapsed,
            'finish_rel': finish_rel,
        })
        
        total_elapsed += elapsed
        max_finish_rel = max(max_finish_rel, finish_rel)
    
    wall_clock = max_finish_rel
    speedup = total_elapsed / wall_clock if wall_clock > 0 else 0.0
    
    print()
    print("=" * 80)
    print(f"Session {session_id} - Execution Statistics")
    print("=" * 80)
    print()
    print(f"{'node':<6} {'skill':<18} {'start (rel)':<12} {'elapsed':<10} {'finish (rel)':<12}")
    print("-" * 80)
    
    for row in rows:
        print(
            f"{row['node']:<6} "
            f"{row['skill']:<18} "
            f"{row['start_rel']:>9.2f} s  "
            f"{row['elapsed']:>7.2f} s  "
            f"{row['finish_rel']:>9.2f} s"
        )
    
    print()
    print(f"wall-clock end-to-end:       {wall_clock:>7.2f} s")
    print(f"sum-of-elapsed (serial):    {total_elapsed:>7.2f} s")
    print(f"parallel speedup ratio:       {speedup:>6.2f}x")
    print("=" * 80)
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
    max_finish_rel = 0.0
    
    for st in timed_nodes:
        start_rel = st.started_at - session_start
        elapsed = st.result.elapsed_s if st.result else 0.0
        finish_rel = start_rel + elapsed
        
        nodes.append({
            'node_id': st.node_id,
            'skill': st.skill,
            'start_rel': start_rel,
            'elapsed': elapsed,
            'finish_rel': finish_rel,
        })
        
        total_elapsed += elapsed
        max_finish_rel = max(max_finish_rel, finish_rel)
    
    wall_clock = max_finish_rel
    speedup = total_elapsed / wall_clock if wall_clock > 0 else 0.0
    
    return {
        'nodes': nodes,
        'wall_clock': wall_clock,
        'total_elapsed': total_elapsed,
        'speedup': speedup
    }
