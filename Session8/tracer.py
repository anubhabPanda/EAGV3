"""
Session 8 Tracer - Formatted trace logging for graph-based agent execution.

Logs:
- Session start with memory hits
- Node execution (skill, inputs, wall clock time)
- Tool calls and results
- Node completion status
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class Session8Tracer:
    """Provides formatted trace logging for Session 8 DAG execution."""

    def __init__(self, enabled: bool = True, log_file: Path | str | None = None,
                 session_id: str = "", query: str = ""):
        """
        Initialize the tracer.

        Args:
            enabled: Whether tracing is enabled (default: True)
            log_file: Path to log file (default: None, no file logging)
            session_id: Session ID for this run
            query: User query for this session
        """
        self.enabled = enabled
        self.log_file = Path(log_file) if log_file else None
        self.session_id = session_id
        self.query = query
        self.node_start_times = {}  # Track wall clock time for each node

        # Write header to log file if provided
        if self.log_file and self.session_id:
            self._write_header()

    def _write_header(self) -> None:
        """Write session header to log file."""
        if not self.log_file:
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        header = f"""
{'=' * 80}
Session ID: {self.session_id}
Timestamp: {timestamp}
Query: {self.query}
{'=' * 80}

"""
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(header)

    def _log(self, text: str) -> None:
        """Print text if tracing is enabled and save to file."""
        if self.enabled:
            print(text)

        # Write to file if log_file is set
        if self.log_file:
            try:
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write(text + '\n')
            except Exception:
                pass

    def session_start(self, session_id: str, query: str, memory_hits: int = 0) -> None:
        """
        Log session start with memory hits.

        Args:
            session_id: Session ID
            query: User query
            memory_hits: Number of memory hits retrieved
        """
        self._log(f"\n{'=' * 78}")
        self._log(f"session {session_id}  -  query: {query}")
        self._log(f"{'=' * 78}")
        if memory_hits > 0:
            self._log(f"[memory.read] {memory_hits} hit(s) visible to every skill this run")

    def memory_read(self, num_hits: int, method: str = "vector") -> None:
        """Log memory read operation."""
        if num_hits == 0:
            self._log(f"[memory.read] no relevant memories found ({method})")
        else:
            self._log(f"[memory.read] {num_hits} hit(s) ({method})")

    def memory_hits_detail(self, hits: list) -> None:
        """Log detailed memory hits."""
        if not hits:
            return
        self._log("[memory.hits]")
        for i, hit in enumerate(hits[:5], 1):  # Show first 5
            descriptor = hit.descriptor if hasattr(hit, 'descriptor') else str(hit)
            display = descriptor if len(descriptor) <= 70 else descriptor[:67] + "..."
            self._log(f"              {i}. {display}")
        if len(hits) > 5:
            self._log(f"              ... and {len(hits) - 5} more")

    def node_start(self, node_id: str, skill: str, inputs: list[str]) -> None:
        """
        Log node execution start.

        Args:
            node_id: Node ID (e.g., "n:1")
            skill: Skill name (e.g., "planner")
            inputs: List of input references
        """
        self.node_start_times[node_id] = datetime.now()
        inputs_display = ", ".join(inputs[:3])
        if len(inputs) > 3:
            inputs_display += f", ... ({len(inputs)} total)"
        self._log(f"[{node_id}] {skill:18s} running...")
        if inputs:
            self._log(f"              inputs: {inputs_display}")

    def tool_call(self, node_id: str, tool_name: str, arguments: dict) -> None:
        """
        Log a tool call from a node.

        Args:
            node_id: Node ID
            tool_name: Tool name
            arguments: Tool arguments
        """
        args_str = json.dumps(arguments, separators=(',', ':'))
        if len(args_str) > 60:
            args_str = args_str[:57] + "..."
        self._log(f"              > tool: {tool_name}({args_str})")

    def tool_result(self, node_id: str, result: str, truncated: bool = False) -> None:
        """
        Log tool execution result.

        Args:
            node_id: Node ID
            result: Tool result text
            truncated: Whether result was truncated
        """
        display_result = result if len(result) <= 70 else result[:67] + "..."
        truncate_marker = " [truncated]" if truncated else ""
        self._log(f"              < result: {display_result}{truncate_marker}")

    def node_complete(self, node_id: str, skill: str, status: str, error: str = None) -> None:
        """
        Log node completion with wall clock time.

        Args:
            node_id: Node ID
            skill: Skill name
            status: Status (complete/failed/skipped)
            error: Error message if failed
        """
        # Calculate elapsed time
        elapsed = 0.0
        if node_id in self.node_start_times:
            elapsed = (datetime.now() - self.node_start_times[node_id]).total_seconds()

        # Format status with wall clock time
        time_str = f"({elapsed:.1f}s)"
        error_msg = f"  err={error[:60]}" if error else ""
        self._log(f"[{node_id}] {skill:18s} {status:8s} {time_str:8s}{error_msg}")

    def node_successors(self, node_id: str, successor_nodes: list[str]) -> None:
        """
        Log successor nodes emitted by a node.

        Args:
            node_id: Node ID that emitted successors
            successor_nodes: List of successor node IDs that were added to the graph
        """
        if not successor_nodes:
            return

        if len(successor_nodes) == 1:
            self._log(f"              + successor: {successor_nodes[0]}")
        else:
            self._log(f"              + successors: {', '.join(successor_nodes)}")

    def final_answer(self, answer: str) -> None:
        """
        Log the final answer.

        Args:
            answer: The final answer text
        """
        self._log(f"\n{'=' * 78}")
        self._log("FINAL:")
        # Show answer (may be multiline)
        for line in answer.split('\n'):
            self._log(line)
        self._log(f"{'=' * 78}\n")

    def separator(self) -> None:
        """Print a blank line separator."""
        self._log('')

    def custom(self, tag: str, message: str) -> None:
        """
        Log a custom message.

        Args:
            tag: Tag in brackets
            message: Message to log
        """
        self._log(f'[{tag}] {message}')

    def graph_status(self, total_nodes: int, completed: int, running: int, pending: int) -> None:
        """
        Log graph execution status.

        Args:
            total_nodes: Total nodes in graph
            completed: Completed nodes
            running: Running nodes
            pending: Pending nodes
        """
        self._log(f"[graph] {total_nodes} nodes: {completed} complete, {running} running, {pending} pending")

    def finalize(self) -> None:
        """Finalize the trace session."""
        if self.log_file:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            footer = f"\nSession completed at {timestamp}\n{'=' * 80}\n\n"
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(footer)
