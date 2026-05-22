"""
AgentTracer - Clean, formatted trace logging for agent execution.
"""
import json
from typing import Any
from schemas import Goal, MemoryItem, ToolCall


class AgentTracer:
    """Provides formatted trace logging for agent execution steps."""
    
    def __init__(self, enabled: bool = True):
        """
        Initialize the tracer.
        
        Args:
            enabled: Whether tracing is enabled (default: True)
        """
        self.enabled = enabled
        self.current_iteration = 0
    
    def _log(self, text: str) -> None:
        """Print text if tracing is enabled."""
        if self.enabled:
            print(text)
    
    def memory_remember(self, raw_text: str, kind: str, keywords: list[str]) -> None:
        """
        Log a memory.remember() call.
        
        Args:
            raw_text: The text being remembered
            kind: The memory kind (fact, preference, etc.)
            keywords: Extracted keywords
        """
        # Truncate text if too long
        display_text = raw_text if len(raw_text) <= 60 else raw_text[:57] + "..."
        
        self._log(f'[memory.remember]  classified "{display_text}" as {kind}')
        self._log(f'                   keywords: {json.dumps(keywords)}')
        self._log('')
    
    def iteration_start(self, iteration: int) -> None:
        """
        Log the start of an iteration.
        
        Args:
            iteration: Iteration number
        """
        self.current_iteration = iteration
        self._log(f'─── iter {iteration} ───')
    
    def perception(self, goals: list[Goal], next_unfinished: Goal | None) -> None:
        """
        Log perception output (goals).
        
        Args:
            goals: List of all goals
            next_unfinished: The next unfinished goal
        """
        if not goals:
            self._log('[perception]    (no goals)')
            return
        
        for i, goal in enumerate(goals, 1):
            status = "✓ done" if goal.done else "open"
            # Truncate goal text if too long
            goal_text = goal.text if len(goal.text) <= 50 else goal.text[:47] + "..."
            
            # Highlight the next unfinished goal
            prefix = '[perception]    ' if i == 1 else '                '
            marker = '→' if next_unfinished and goal.id == next_unfinished.id else ' '
            
            artifact_note = f" (artifact: {goal.attach_artifact_id})" if goal.attach_artifact_id else ""
            
            self._log(f'{prefix}{marker}[{status}] Goal {i}: {goal_text}{artifact_note}')
    
    def decision_tool_call(self, tool_call: ToolCall) -> None:
        """
        Log a decision to call a tool.
        
        Args:
            tool_call: The tool call decision
        """
        # Format arguments compactly
        args_str = json.dumps(tool_call.arguments, separators=(',', ':'))
        if len(args_str) > 80:
            args_str = args_str[:77] + "..."
        
        self._log(f'[decision]      TOOL_CALL: {tool_call.name}({args_str})')
    
    def decision_answer(self, answer: str) -> None:
        """
        Log a decision to provide an answer.
        
        Args:
            answer: The answer text
        """
        # Show first line or truncate
        first_line = answer.split('\n')[0]
        if len(first_line) > 70:
            first_line = first_line[:67] + "..."
        
        self._log(f'[decision]      ANSWER: {first_line}')
        if '\n' in answer:
            self._log(f'                (multi-line answer, {len(answer)} chars total)')
    
    def action_result(self, success: bool, message: str = "", artifact_id: str | None = None) -> None:
        """
        Log action execution result.
        
        Args:
            success: Whether the action succeeded
            message: Result message or error
            artifact_id: Artifact ID if created
        """
        if success:
            if artifact_id:
                self._log(f'[action]        → ok (artifact: {artifact_id})')
            elif message:
                # Truncate message
                display_msg = message if len(message) <= 60 else message[:57] + "..."
                self._log(f'[action]        → ok: {display_msg}')
            else:
                self._log(f'[action]        → ok')
        else:
            # Show error message
            display_msg = message if len(message) <= 60 else message[:57] + "..."
            self._log(f'[action]        → ERROR: {display_msg}')
    
    def final_answer(self, answer: str) -> None:
        """
        Log the final answer.
        
        Args:
            answer: The final answer text
        """
        self._log('')
        self._log('─── FINAL ANSWER ───')
        self._log(answer)
        self._log('')
    
    def separator(self) -> None:
        """Print a blank line separator."""
        self._log('')
    
    def custom(self, tag: str, message: str, indent: bool = False) -> None:
        """
        Log a custom message.
        
        Args:
            tag: Tag in brackets (e.g., "system", "debug")
            message: Message to log
            indent: Whether to indent the message
        """
        prefix = f'[{tag}]'
        if indent:
            prefix = prefix.ljust(16)
        self._log(f'{prefix} {message}')
