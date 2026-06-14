#!/usr/bin/env python3
"""Generate ASCII visualization of the execution DAG from graph.json.

Usage:
    python visualize_graph.py <session_id>
"""

import sys
import json
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, errors='replace')


def visualize_dag(session_id: str) -> str:
    """Create ASCII art visualization of the DAG."""
    graph_path = Path(__file__).parent / "state" / "sessions" / session_id / "graph.json"
    
    if not graph_path.exists():
        return f"Error: Session {session_id} not found"
    
    with open(graph_path, encoding='utf-8') as f:
        data = json.load(f)
    
    nodes = {n['id']: n for n in data['nodes']}
    edges = [(e['source'], e['target']) for e in data['edges']]
    
    # Build adjacency list
    children = {nid: [] for nid in nodes}
    for src, tgt in edges:
        children[src].append(tgt)
    
    # Build visualization
    lines = []
    lines.append("```")
    lines.append("Execution DAG Visualization")
    lines.append("=" * 70)
    lines.append("")
    
    def format_node(nid):
        node = nodes[nid]
        skill = node['skill']
        status = node.get('status', 'pending')
        
        elapsed = ""
        if node.get('result'):
            elapsed_s = node['result'].get('elapsed_s', 0)
            elapsed = f" ({elapsed_s:.1f}s)"
        
        status_icon = {
            'complete': '✓',
            'failed': '✗',
            'running': '▶',
            'pending': '○'
        }.get(status, '?')
        
        return f"{nid} [{skill}]{elapsed} {status_icon}"
    
    # Topological traversal
    visited = set()
    
    def traverse(nid, prefix="", is_last=True):
        if nid in visited:
            return
        visited.add(nid)
        
        connector = "└─ " if is_last else "├─ "
        lines.append(f"{prefix}{connector}{format_node(nid)}")
        
        child_nodes = children.get(nid, [])
        for i, child in enumerate(child_nodes):
            is_last_child = (i == len(child_nodes) - 1)
            extension = "   " if is_last else "│  "
            traverse(child, prefix + extension, is_last_child)
    
    # Find root (node with no incoming edges)
    all_targets = {e[1] for e in edges}
    roots = [nid for nid in nodes if nid not in all_targets]
    
    for root in roots:
        traverse(root)
    
    lines.append("")
    lines.append("Legend:")
    lines.append("  ✓ = complete  ✗ = failed  ▶ = running  ○ = pending")
    lines.append("```")
    
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python visualize_graph.py <session_id>")
        sys.exit(1)
    
    session_id = sys.argv[1]
    print(visualize_dag(session_id))


if __name__ == "__main__":
    main()
