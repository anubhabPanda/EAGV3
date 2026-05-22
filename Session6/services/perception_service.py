import sys
import json
from pathlib import Path

# Add parent directory to path to import schemas
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schemas import MemoryItem, Goal, Observation

# Add llm_gatewayV3 to path
gateway_path = Path(__file__).resolve().parent.parent.parent / "resources" / "llm_gatewayV3"
sys.path.insert(0, str(gateway_path))

from client import LLM


def build_perception_prompt(
    query: str,
    hits: list[MemoryItem],
    history: list[dict],
    prior_goals: list[Goal],
) -> str:
    """
    Build the perception prompt for goal decomposition and tracking.

    This prompt instructs the LLM to:
    1. Decompose the query into bounded goals (if prior_goals is empty)
    2. Mark goals as done based on history
    3. Attach artifact IDs to the first unfinished goal if needed
    4. Preserve goal order

    Args:
        query: The user's query string
        hits: List of relevant memory items retrieved
        history: Conversation/action history
        prior_goals: Previously established goals

    Returns:
        The formatted prompt string
    """
    # Format memory hits
    memory_section = "MEMORY HITS:\n"
    if hits:
        for i, hit in enumerate(hits, 1):
            memory_section += f"{i}. [{hit.kind}] {hit.descriptor}\n"
            memory_section += f"   Keywords: {', '.join(hit.keywords)}\n"
            if hit.artifact_id is not None:
                memory_section += f"   Artifact ID: {hit.artifact_id}\n"
            memory_section += f"   Source: {hit.source}\n"
            memory_section += f"   Confidence: {hit.confidence}\n"
            memory_section += "\n"
    else:
        memory_section += "(No relevant memories found)\n\n"

    # Format history
    history_section = "RUN HISTORY:\n"
    if history:
        for i, entry in enumerate(history, 1):
            role = entry.get("role", "unknown")
            content = entry.get("content", "")
            tool_calls = entry.get("tool_calls", [])
            tool_name = entry.get("tool_name", "")

            if role == "user":
                history_section += f"{i}. [USER] {content}\n"
            elif role == "assistant":
                if tool_calls:
                    for tc in tool_calls:
                        history_section += f"{i}. [ASSISTANT → TOOL] {tc['name']}({json.dumps(tc.get('arguments', {}))})\n"
                elif content:
                    history_section += f"{i}. [ASSISTANT] {content}\n"
            elif role == "tool":
                history_section += f"{i}. [TOOL → {tool_name}] {content[:100]}{'...' if len(content) > 100 else ''}\n"
            else:
                history_section += f"{i}. [{role.upper()}] {str(entry)[:100]}\n"
    else:
        history_section += "(No history yet)\n"
    history_section += "\n"

    # Format prior goals
    prior_goals_section = "PRIOR GOALS:\n"
    if prior_goals:
        for i, goal in enumerate(prior_goals, 1):
            status = "✓ DONE" if goal.done else "⧗ PENDING"
            artifact_note = f" [artifact: {goal.attach_artifact_id}]" if goal.attach_artifact_id else ""
            prior_goals_section += f"{i}. [{status}] {goal.text}{artifact_note}\n"
    else:
        prior_goals_section += "(No prior goals - you must create initial goals)\n"
    prior_goals_section += "\n"

    # Build the full prompt
    prompt = f"""You are the Perception module of an agentic system. Your job is to maintain a goal list and track progress.

USER QUERY:
{query}

{memory_section}
{history_section}
{prior_goals_section}

REASONING TYPE AWARENESS:

Classify what type of reasoning this request requires:
- **PLANNING**: Query requires decomposition into goals (e.g., "How do I X?", "Tell me about Y")
- **RETRIEVAL**: Query needs information from memory/artifacts (e.g., "What did I ask earlier?")
- **EXTRACTION**: Query needs parsing/extracting from fetched content (e.g., "What year was X?")
- **VERIFICATION**: Query checks completion or validates state (e.g., "Did we finish?", "Is this done?")

Your primary reasoning type for this request: [State it explicitly before proceeding]

INSTRUCTIONS:

1. **If PRIOR GOALS is empty:** Decompose the user query into one or more bounded goals.
   Each goal must be a short imperative statement (e.g., "Fetch the Wikipedia page for Apollo 11").
   Create a clear, sequential plan. Do not do arithmetic or make assumptions about goals descriptions.

2. **If PRIOR GOALS exist:** For each prior goal, examine the RUN HISTORY.
   Mark the goal `done: true` the moment the history contains an action that satisfies it.
   Once done, the goal remains done in every subsequent iteration.
   DO NOT unmark a completed goal.

3. **For the first unfinished goal:** Decide whether it needs raw bytes from a previously
   fetched artifact. If yes, set the goal's `attach_artifact_id` to one of the artifact IDs
   shown in MEMORY HITS above. Only attach artifacts that are relevant to THIS specific goal.

4. **Preserve goal order:** Do NOT reorder goals. Do NOT insert goals in the middle of the list.
   Do NOT drop a goal. Keep the exact same order. You may only:
   - Add new goals at the END
   - Mark existing goals as done
   - Attach artifact IDs to goals

5. **Output format:** Return an Observation object with:
   - `goals`: The complete list of goals (in order)
   - `next_unfinished`: The first goal in the list where `done: false`, or null if all are done

INTERNAL SELF-CHECKS (verify before output):

□ **Consistency check**: Is `next_unfinished` actually the first goal in `goals` where `done: false`?
  If all goals are done, is `next_unfinished` set to null?

□ **Completion integrity**: Have you verified that no completed goal (done: true) has been
  reverted to done: false? Once done, always done.

□ **Order preservation**: Are the goals in the exact same order as PRIOR GOALS?
  Have you only added new goals at the END, never inserted or reordered?

□ **Artifact validity**: If you attached an artifact_id to a goal, does that artifact ID
  actually appear in MEMORY HITS above? Is it relevant to that specific goal?

□ **Evidence-based completion**: For each goal marked done: true, can you point to specific
  evidence in RUN HISTORY that satisfies it? No speculation.

□ **Goal quality**: Is each goal a clear, actionable, bounded imperative statement?
  Avoid vague goals like "understand X" - prefer "fetch X" or "extract Y from X".

FALLBACK BEHAVIORS (handle edge cases):

**If history is ambiguous:**
- Be conservative: only mark a goal done if there's CLEAR evidence
- If uncertain whether a goal is satisfied, leave it as done: false
- Add a note in your reasoning about the ambiguity

**If an artifact is missing:**
- If a goal needs an artifact but none are in MEMORY HITS, set attach_artifact_id to null
- The goal can still proceed - the Decision module will handle fetching
- Only attach artifacts that already exist

**If evidence is conflicting:**
- Prioritize the most recent history entry
- If a tool call failed, the goal is NOT done even if attempted
- Tool success (not just invocation) is required for completion

**If prior goals are malformed:**
- If a prior goal has an invalid structure, preserve it but flag in reasoning
- Do not drop malformed goals - maintain continuity
- Fix only what's necessary (e.g., missing fields)

**If you're uncertain:**
- Default to conservative choices (don't mark done if unsure)
- Preserve existing state rather than making risky changes
- Uncertainty is acceptable - be honest in your reasoning

**If no prior goals and query is unclear:**
- Create one broad exploratory goal (e.g., "Understand the user's intent")
- This can be refined in subsequent iterations
- Better to have a safe starting point than to guess wrong

RESPONSE FORMAT:

Before outputting the Observation object, provide your reasoning in this structure:

1. **Reasoning type**: [PLANNING | RETRIEVAL | EXTRACTION | VERIFICATION]
2. **Current state analysis**: What has been accomplished? What remains?
3. **Evidence review**: For each goal marked done, cite the specific history entry
4. **Self-check results**: Walk through each checkbox above
5. **Edge cases encountered**: Any ambiguity, missing data, or conflicts?
6. **Final decision**: Why this goal list is correct

Then output the Observation object:

{{
  "goals": [
    {{"id": "goal:1", "text": "Fetch Apollo 11 landing page", "done": true, "attach_artifact_id": null}},
    {{"id": "goal:2", "text": "Extract the landing year", "done": false, "attach_artifact_id": 5}}
  ],
  "next_unfinished": {{"id": "goal:2", "text": "Extract the landing year", "done": false, "attach_artifact_id": 5}}
}}

CRITICAL REMINDERS:
- Run ALL self-checks before output - they catch 90% of errors
- Evidence-based decisions only - never speculate about completion
- Conservative over aggressive - preserve state when uncertain
- Artifact IDs must exist in MEMORY HITS to be valid
- Goal completion is irreversible - verify before marking done: true
- Order is sacred - never reorder, insert, or drop goals
- Be explicit about your reasoning type and edge cases
"""

    return prompt


class Perception:
    def __init__(self, llm: LLM = None):
        """
        Initialize the Perception service.

        Args:
            llm: Optional LLM client instance (defaults to new LLM())
        """
        self.llm = llm if llm is not None else LLM()

    def observe(
        self,
        query: str,
        hits: list[MemoryItem],
        history: list[dict],
        prior_goals: list[Goal],
        run_id: str,
    ) -> Observation:
        """
        Observe the current state and update goals.

        Uses the LLM Gateway V3 with structured output to return a validated
        Observation object containing the updated goal list.

        Args:
            query: The user's query
            hits: Relevant memory items
            history: Conversation/action history
            prior_goals: Previously established goals
            run_id: Current run identifier

        Returns:
            Observation with updated goals
        """
        # Build the perception prompt
        prompt = build_perception_prompt(
            query=query,
            hits=hits,
            history=history,
            prior_goals=prior_goals,
        )

        # Get the Observation schema for structured output
        observation_schema = Observation.model_json_schema()

        # Call LLM Gateway V3 with structured output
        response = self.llm.chat(
            prompt=prompt,
            auto_route="perception",
            provider="g", # Pins to Gemini
            response_format={
                "type": "json_schema",
                "schema": observation_schema,
                "name": "Observation",
                "strict": True,
            },
            temperature=0,
            max_tokens=8192,
        )

        # Parse the structured response
        if response.get("parsed"):
            # The gateway already validated against the schema
            observation = Observation.model_validate(response["parsed"])
        else:
            # Fallback: try to parse from text
            text = response.get("text", "")
            try:
                # Try to extract JSON from the text
                import re
                json_match = re.search(r'\{.*\}', text, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group(0))
                    observation = Observation.model_validate(data)
                else:
                    raise ValueError("No JSON found in response")
            except (json.JSONDecodeError, ValueError) as e:
                # Last resort: return empty observation
                observation = Observation(goals=prior_goals, next_unfinished=None)

        return observation