import sys
import json
from pathlib import Path

# Add parent directory to path to import schemas
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schemas import MemoryItem, Goal, DecisionOutput, ToolCall

# Add llm_gatewayV3 to path
gateway_path = Path(__file__).resolve().parent.parent.parent / "resources" / "llm_gatewayV3"
sys.path.insert(0, str(gateway_path))

from client import LLM


def build_decision_prompt(
    goal: Goal,
    hits: list[MemoryItem],
    attached: list[tuple[str, bytes]],
    history: list[dict],
) -> str:
    """
    Build the decision prompt for choosing the next action.
    
    Args:
        goal: The current goal to accomplish
        hits: Relevant memory items
        attached: List of (artifact_id, raw_bytes) tuples for artifacts attached to this goal
        history: Conversation/action history
    
    Returns:
        The formatted prompt string
    """
    # Format memory hits
    memory_section = "MEMORY CONTEXT:\n"
    if hits:
        for i, hit in enumerate(hits, 1):
            memory_section += f"{i}. [{hit.kind}] {hit.descriptor}\n"
            if hit.artifact_id is not None:
                memory_section += f"   Artifact ID: {hit.artifact_id}\n"
            memory_section += f"   Source: {hit.source}\n"
    else:
        memory_section += "(No relevant memories)\n"
    memory_section += "\n"
    
    # Format attached artifacts
    attached_section = "ATTACHED ARTIFACTS:\n"
    if attached:
        for artifact_id, raw_bytes in attached:
            try:
                # Try to decode as text
                content = raw_bytes.decode('utf-8', errors='replace')
                # Truncate very long content
                if len(content) > 10000:
                    content = content[:10000] + f"\n\n[...truncated, {len(raw_bytes)} bytes total]"
                attached_section += f"--- Artifact {artifact_id} ---\n{content}\n\n"
            except Exception:
                attached_section += f"--- Artifact {artifact_id} ---\n[Binary content, {len(raw_bytes)} bytes]\n\n"
    else:
        attached_section += "(No artifacts attached to this goal)\n"
    attached_section += "\n"
    
    # Format history
    history_section = "ACTION HISTORY:\n"
    if history:
        for i, entry in enumerate(history[-10:], 1):  # Last 10 entries
            role = entry.get("role", "unknown")
            content = entry.get("content", "")
            tool_calls = entry.get("tool_calls", [])
            tool_name = entry.get("tool_name", "")
            
            if role == "user":
                history_section += f"{i}. [USER] {content}\n"
            elif role == "assistant":
                if tool_calls:
                    for tc in tool_calls:
                        history_section += f"{i}. [TOOL CALL] {tc['name']}({json.dumps(tc.get('arguments', {}))})\n"
                elif content:
                    history_section += f"{i}. [ANSWER] {content[:200]}{'...' if len(content) > 200 else ''}\n"
            elif role == "tool":
                history_section += f"{i}. [TOOL RESULT → {tool_name}] {content[:150]}{'...' if len(content) > 150 else ''}\n"
    else:
        history_section += "(No prior actions)\n"
    history_section += "\n"
    
    # Build the system prompt with three substantive instructions
    system_prompt = """You are the Decision module of an agentic system. Your job is to accomplish the current goal by choosing the next action.

CRITICAL INSTRUCTIONS:

1. **Choice Rule — Exactly One Output:**
   You must respond with EXACTLY ONE of these two outputs:
   - **Tool Call**: Call one MCP tool to take an action (fetch data, create file, search, etc.)
   - **Answer**: Provide the final answer if the goal is fully satisfied

   DO NOT do both. DO NOT provide meta-commentary. Choose one.

2. **Artifact Handle Rule — art: prefix is internal:**
   Artifact IDs have the format "art:<number>" (e.g., "art:1", "art:5", "art:127").
   They reference the internal artifact store and are NOT file paths or URLs.

   - MCP tools (read_file, fetch_url, etc.) accept REAL file paths and URLs only
   - They REJECT artifact IDs (art:...) at dispatch time
   - When a goal requires artifact bytes, those bytes appear in ATTACHED ARTIFACTS below
   - Read the content there — DO NOT pass artifact IDs to MCP tools

   Example:
   ❌ WRONG: read_file("art:5") or fetch_url("art:1") or read_file(5)
   ✓ RIGHT: Read the content from "ATTACHED ARTIFACTS: Artifact art:5" section below

   If you see "Artifact ID: art:5" in MEMORY CONTEXT, that means artifact art:5's bytes are
   already available in ATTACHED ARTIFACTS. You don't need to fetch it.

3. **Substantive Answer Rule — No meta-answers:**
   When the goal asks for extraction, analysis, comparison, or selection:
   - Provide a SUBSTANTIVE answer (at least 3 sentences or a list of items)
   - DO NOT say "the page has been fetched, how would you like to proceed?"
   - DO NOT provide meta-commentary about what you could do
   - DO the actual work the goal requires and provide the result
   
   Example goal: "Extract the landing year from the Apollo 11 page"
   ❌ WRONG: "The page content is available. What would you like to know?"
   ✓ RIGHT: "The Apollo 11 mission landed on the Moon on July 20, 1969. This historic event..."

INTERNAL SELF-CHECKS (verify before output):

□ **Goal satisfaction check**: Is the goal ALREADY satisfied by the ACTION HISTORY?
  If a prior tool call already fetched/created what's needed, don't repeat it.
  If extraction is needed and artifacts are attached, extract NOW (don't defer).

□ **Artifact availability check**: Does the goal reference an artifact ID in ATTACHED ARTIFACTS?
  If yes, the bytes are RIGHT THERE in the prompt. Read and process them.
  DO NOT call read_file() or fetch_url() with the artifact ID.

□ **Tool argument validity**: If calling a tool, are the arguments REAL paths/URLs?
  ❌ Invalid: read_file("art:5"), fetch_url("art:127"), read_file("artifact 3")
  ✓ Valid: fetch_url("https://..."), read_file("notes.txt"), web_search("query")

□ **Answer substantiveness**: If providing an answer, is it substantive?
  For extraction goals: Did you actually extract the information?
  For list goals: Did you provide the actual list?
  For comparison goals: Did you compare and state the result?

□ **One output only**: Am I returning EITHER a tool call OR an answer (not both)?
  Am I avoiding meta-commentary like "I could..." or "Next we should..."?

FALLBACK BEHAVIORS (handle edge cases):

**If the goal is ambiguous:**
- Make a reasonable interpretation based on context
- If truly unclear, call web_search or list_dir to gather more context
- Don't provide a meta-answer asking for clarification

**If required data is missing:**
- Identify what data source would help (URL, search query, file path)
- Call the appropriate fetch tool (fetch_url, web_search, read_file, list_dir)
- Don't say "I need more information" - go get it

**If artifacts are attached but content is unclear:**
- Process what's there to the best of your ability
- If the artifact is binary/corrupted, acknowledge it in your answer
- Don't fail silently - provide what you can extract

**If history shows a prior tool call failed:**
- Don't retry the exact same call with the exact same arguments
- Try a different approach (different search terms, different tool, etc.)
- If truly stuck, provide a partial answer with what you know

**If multiple tools could work:**
- Choose the most direct tool for the goal
- Prefer fetch_url for known URLs over web_search
- Prefer read_file for known paths over list_dir then read_file

**If you're uncertain about the answer:**
- Provide your best interpretation with confidence levels
- Better to give a reasoned answer than to defer
- Uncertainty is acceptable - meta-answers are not

REMEMBER:
- One action per step (tool call OR answer)
- Never pass artifact IDs (art:...) to MCP tools
- Substantive answers, not meta-commentary
- Run all self-checks before output
- Handle edge cases with fallback behaviors, not deferrals
"""
    
    # Build the user prompt
    prompt = f"""{memory_section}{attached_section}{history_section}

CURRENT GOAL:
{goal.text}

Based on the goal, memory context, attached artifacts, and action history, choose your next step:
- If you need more data: call an appropriate MCP tool
- If the goal is satisfied: provide the final answer

What is your next action?"""

    return system_prompt, prompt


class Decision:
    def __init__(self, llm: LLM = None):
        """
        Initialize the Decision service.
        
        Args:
            llm: Optional LLM client instance (defaults to new LLM())
        """
        self.llm = llm if llm is not None else LLM()
    
    def next_step(
        self,
        goal: Goal,
        hits: list[MemoryItem],
        attached: list[tuple[str, bytes]],
        history: list[dict],
        mcp_tools: list[dict],
    ) -> DecisionOutput:
        """
        Decide the next action to accomplish the goal.
        
        Uses LLM Gateway V3 with decision routing and native tool use.
        Returns either a tool call or a final answer.
        
        Args:
            goal: The current goal to accomplish
            hits: Relevant memory items
            attached: List of (artifact_id, raw_bytes) tuples
            history: Action history
            mcp_tools: Available MCP tools in gateway format
        
        Returns:
            DecisionOutput with either answer or tool_call populated (not both)
        """
        # Build the decision prompt (returns tuple: system, user)
        system_prompt, user_prompt = build_decision_prompt(
            goal=goal,
            hits=hits,
            attached=attached,
            history=history,
        )

        print("\n--- DECISION SYSTEM PROMPT ---")
        print(system_prompt + "\n" + user_prompt)

        # Call LLM Gateway V3 with decision routing and tool use
        # When tools are provided, the gateway returns native tool_calls
        # When no tool is called, we want structured DecisionOutput with answer
        response = self.llm.chat(
            prompt=user_prompt,
            system=system_prompt,
            auto_route="decision",
            tools=mcp_tools,
            tool_choice="auto",
            temperature=0,
            max_tokens=2048,
        )

        # Parse response: tool_calls OR text
        tool_calls = response.get("tool_calls") or []
        text = response.get("text", "").strip()

        if tool_calls:
            # Return the first tool call wrapped in ToolCall
            first_call = tool_calls[0]
            return DecisionOutput(
                answer=None,
                tool_call=ToolCall(
                    name=first_call["name"],
                    arguments=first_call.get("arguments", {})
                )
            )
        else:
            # Return the text as the answer
            return DecisionOutput(
                answer=text if text else None,
                tool_call=None
            )
