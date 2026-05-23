import sys
import hashlib
import json
from pathlib import Path
from datetime import datetime
from collections import Counter
from pydantic import BaseModel
from typing import Literal

# Add parent directory to path to import schemas
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schemas import MemoryItem, ToolCall

# Add llm_gatewayV3 to path
gateway_path = Path(__file__).resolve().parent.parent.parent / "resources" / "llm_gatewayV3"
sys.path.insert(0, str(gateway_path))

from client import LLM


class MemoryExtraction(BaseModel):
    """Schema for LLM-extracted memory information."""
    kind: Literal["fact", "preference", "tool_outcome", "scratchpad"]
    keywords: list[str]
    descriptor: str
    value: dict


class Memory:
    def __init__(self, storage: list[MemoryItem] = None, memory_file: str | Path = None, llm: LLM = None):
        """
        Initialize the Memory service.

        Args:
            storage: Optional list of MemoryItem objects to initialize the memory with
            memory_file: Path to the JSON file for persistence (default: state/memory.json)
            llm: Optional LLM client instance (defaults to new LLM())
        """
        # Set up the memory file path
        if memory_file is None:
            # Default to state/memory.json relative to the Session6 directory
            file_dir = Path(__file__).resolve().parent.parent
            self.memory_file = file_dir / "state" / "memory.json"
        else:
            self.memory_file = Path(memory_file)

        # Ensure state directory exists
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)

        # Set up LLM client
        self.llm = llm if llm is not None else LLM()

        # Load from file if it exists, otherwise use provided storage
        if storage is not None:
            self.storage: list[MemoryItem] = storage
        else:
            self.storage = self._load_from_file()

        # Build deduplication index: raw_text -> memory_item_id
        # This makes duplicate detection O(1) instead of O(n)
        self._text_index: dict[str, str] = {}
        self._rebuild_index()
    
    def read(
        self,
        query: str,
        history: list[dict],
        kinds: list[str] | None = None,
        top_k: int = 8
    ) -> list[MemoryItem]:
        """
        Read relevant memory items based on keyword overlap.
        
        Performs keyword overlap matching across:
        - The keywords field of each MemoryItem
        - Tokens from the descriptor field
        
        Returns the top-k ranked results.
        
        Args:
            query: The search query string
            history: Conversation history (list of message dicts)
            kinds: Optional list of memory kinds to filter by 
                   (e.g., ["fact", "preference", "tool_outcome", "scratchpad"])
            top_k: Number of top results to return (default: 8)
        
        Returns:
            List of top-k MemoryItem objects ranked by relevance
        """
        # Tokenize the query into lowercase words
        query_tokens = set(query.lower().split())
        
        # Filter by kinds if specified
        candidates = self.storage
        if kinds is not None:
            candidates = [item for item in candidates if item.kind in kinds]
        
        # Score each memory item
        scored_items: list[tuple[MemoryItem, float]] = []
        
        for item in candidates:
            score = self._compute_overlap_score(item, query_tokens)
            scored_items.append((item, score))
        
        # Sort by score (descending) and take top-k
        scored_items.sort(key=lambda x: x[1], reverse=True)
        top_items = [item for item, score in scored_items[:top_k]]
        
        return top_items
    
    def _compute_overlap_score(self, item: MemoryItem, query_tokens: set[str]) -> float:
        """
        Compute overlap score for a memory item based on keyword matching.
        
        Combines:
        - Keywords from the item's keywords field
        - Tokens from the item's descriptor field
        
        Args:
            item: The MemoryItem to score
            query_tokens: Set of lowercase query tokens
        
        Returns:
            Overlap score (higher is better)
        """
        # Get keywords (convert to lowercase)
        item_keywords = set(kw.lower() for kw in item.keywords)
        
        # Get descriptor tokens (convert to lowercase and split)
        descriptor_tokens = set(item.descriptor.lower().split())
        
        # Combine keywords and descriptor tokens
        item_tokens = item_keywords | descriptor_tokens
        
        # Calculate overlap
        overlap = query_tokens & item_tokens
        
        # Score is the size of the overlap
        # Could be enhanced with weights, TF-IDF, etc.
        score = len(overlap)
        
        return score
    
    def _rebuild_index(self) -> None:
        """
        Rebuild the text-to-id index from current storage.
        Call this after loading from file or bulk operations.
        """
        self._text_index.clear()
        for item in self.storage:
            raw_text = item.value.get("raw_text", "")
            if raw_text:
                self._text_index[raw_text] = item.id

    def add(self, item: MemoryItem) -> None:
        """
        Add a memory item to storage and persist to file.
        Also updates the deduplication index.

        Args:
            item: The MemoryItem to add
        """
        self.storage.append(item)

        # Update index
        raw_text = item.value.get("raw_text", "")
        if raw_text:
            self._text_index[raw_text] = item.id

        self._save_to_file()

    def clear(self) -> None:
        """Clear all memory items from storage, file, and index."""
        self.storage.clear()
        self._text_index.clear()
        self._save_to_file()

    def __len__(self) -> int:
        """Return the number of items in memory."""
        return len(self.storage)

    def deduplicate(self) -> int:
        """
        Remove duplicate memories based on raw_text content.
        Keeps the most recent version (latest created_at).
        Rebuilds the index after deduplication.

        Returns:
            Number of duplicates removed
        """
        seen_texts = {}
        unique_items = []
        duplicates_removed = 0

        # Sort by created_at (oldest first) so we keep the newest
        sorted_items = sorted(self.storage, key=lambda x: x.created_at)

        for item in sorted_items:
            raw_text = item.value.get("raw_text", "")

            if raw_text in seen_texts:
                # Duplicate found - skip this older version
                duplicates_removed += 1
            else:
                # First occurrence of this text
                seen_texts[raw_text] = item.id
                unique_items.append(item)

        # Update storage with deduplicated list
        self.storage = unique_items

        # Rebuild index after deduplication
        self._rebuild_index()

        # Save to file
        if duplicates_removed > 0:
            self._save_to_file()

        return duplicates_removed

    def _load_from_file(self) -> list[MemoryItem]:
        """
        Load memory items from the JSON file.

        Returns:
            List of MemoryItem objects loaded from file, or empty list if file doesn't exist
        """
        if not self.memory_file.exists():
            return []

        try:
            with open(self.memory_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Convert JSON dicts back to MemoryItem objects
            items = []
            for item_dict in data:
                # Parse datetime strings back to datetime objects
                if 'created_at' in item_dict and isinstance(item_dict['created_at'], str):
                    item_dict['created_at'] = datetime.fromisoformat(item_dict['created_at'])
                items.append(MemoryItem(**item_dict))

            return items

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            # Silently return empty list on load failure
            return []

    def _save_to_file(self) -> None:
        """
        Save all memory items to the JSON file.

        Persists the current state of memory to disk.
        """
        try:
            # Convert MemoryItem objects to dicts
            data = []
            for item in self.storage:
                item_dict = item.model_dump()
                # Convert datetime to ISO format string for JSON serialization
                if 'created_at' in item_dict and isinstance(item_dict['created_at'], datetime):
                    item_dict['created_at'] = item_dict['created_at'].isoformat()
                data.append(item_dict)

            # Write to file with pretty formatting
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            # Silently fail on save error
            pass

    def remember(
        self,
        raw_text: str,
        source: str,
        run_id: str,
        goal_id: str | None = None
    ) -> MemoryItem:
        """
        Store free-form ambiguous content (user input, observed statement).

        Uses LLM (Gemini, auto_route="memory") to intelligently classify and extract:
        - kind: fact | preference | tool_outcome | scratchpad
        - keywords: relevant searchable terms
        - descriptor: short one-line summary
        - value: structured data extracted from the text

        Deduplication: Checks if similar content already exists based on raw_text.
        If found, updates run_id and returns existing item instead of creating duplicate.

        Args:
            raw_text: The free-form text content to remember
            source: Source identifier (e.g., "user_input", "observation", "system")
            run_id: Unique identifier for the current agent run
            goal_id: Optional identifier for the associated goal

        Returns:
            The created or existing MemoryItem
        """
        # O(1) duplicate check using index
        if raw_text in self._text_index:
            # Found duplicate - retrieve existing item by ID
            existing_id = self._text_index[raw_text]
            existing_item = next((item for item in self.storage if item.id == existing_id), None)

            if existing_item:
                # Found duplicate - return existing item
                # Optionally update run_id to track latest access
                # existing_item.run_id = run_id  # Uncomment if you want to track latest run
                return existing_item
        # Build classification prompt
        prompt = f"""You are the Memory classification module. Analyze the following text and extract structured memory information.

TEXT TO REMEMBER:
{raw_text}

SOURCE: {source}

TASK:
Classify this text and extract the following:

1. **kind**: Choose ONE category:
   - "fact": Objective information, data, events (e.g., "Apollo 11 landed in 1969", "My birthday is May 15")
   - "preference": User likes, dislikes, or preferences (e.g., "I prefer coffee over tea")
   - "tool_outcome": Result from a tool/action (only if this looks like a tool result)
   - "scratchpad": Temporary notes, working memory, intermediate thoughts

2. **keywords**: Extract 3-10 searchable keywords. Rules:
   - Use lowercase
   - Remove possessives: "John's" → "john"
   - Include dates, names, numbers as separate tokens
   - Include month names: "may", "june", etc.
   - Remove stop words: "the", "a", "is", "was", etc.

3. **descriptor**: One-line summary (max 100 chars), clear and specific
   - Good: "John's birthday: May 15, 2026"
   - Bad: "Information about a birthday"

4. **value**: Structured extraction as a JSON object. Extract:
   - Dates in ISO format if present
   - Names, numbers, entities (named entities)
   - Key facts as key-value pairs
   - Example: {{"value": "2026-05-15", "entity": "John", "attribute": "birthday"}}

RESPOND WITH:
A MemoryExtraction object with all four fields populated.
"""

        # Get schema for structured output
        schema = MemoryExtraction.model_json_schema()

        # Call LLM with memory routing (with retry)
        for attempt in range(3):
            try:
                response = self.llm.chat(
                    prompt=prompt,
                    auto_route="memory",
                    response_format={
                        "type": "json_schema",
                        "schema": schema,
                        "name": "MemoryExtraction",
                        "strict": True,
                    },
                    temperature=0,
                    max_tokens=1024,
                )
                break
            except Exception as e:
                if attempt == 2:
                    raise
                continue

        # Parse the structured response
        if response.get("parsed"):
            extraction = MemoryExtraction.model_validate(response["parsed"])
        else:
            # Fallback: manual extraction
            extraction = self._fallback_extraction(raw_text)

        # Generate unique ID
        content_hash = hashlib.sha256(
            f"{raw_text}{source}{run_id}{datetime.now().isoformat()}".encode()
        ).hexdigest()
        item_id = f"mem:{content_hash[:12]}"

        # Ensure raw_text is in value
        if "raw_text" not in extraction.value:
            extraction.value["raw_text"] = raw_text
        if "timestamp" not in extraction.value:
            extraction.value["timestamp"] = datetime.now().isoformat()

        # Create the memory item using LLM-extracted fields
        item = MemoryItem(
            id=item_id,
            kind=extraction.kind,
            keywords=extraction.keywords,
            descriptor=extraction.descriptor,
            value=extraction.value,
            artifact_id=None,
            source=source,
            run_id=run_id,
            goal_id=goal_id,
            confidence=0.85,  # Higher confidence with LLM classification
            created_at=datetime.now()
        )

        # Add to storage
        self.add(item)

        return item

    def _fallback_extraction(self, raw_text: str) -> MemoryExtraction:
        """
        Fallback extraction when LLM structured output fails.
        Uses simple heuristics.
        """
        # Simple keyword extraction
        stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will", "would",
            "could", "should", "might", "can", "i", "you", "he", "she", "it",
            "we", "they", "this", "that", "these", "those", "my", "your", "his", "her"
        }

        tokens = raw_text.lower().split()
        keywords = []

        for token in tokens:
            cleaned = token.strip(".,!?;:()[]{}\"'")
            if cleaned.endswith("'s"):
                cleaned = cleaned[:-2]
            elif cleaned.endswith("s'"):
                cleaned = cleaned[:-2]
            if len(cleaned) > 1 and cleaned not in stop_words:
                keywords.append(cleaned)

        keyword_counts = Counter(keywords)
        top_keywords = [kw for kw, _ in keyword_counts.most_common(10)]

        # Simple descriptor
        descriptor = raw_text[:100]
        if len(raw_text) > 100:
            descriptor = raw_text[:97] + "..."

        return MemoryExtraction(
            kind="fact",
            keywords=top_keywords,
            descriptor=descriptor,
            value={"raw_text": raw_text, "timestamp": datetime.now().isoformat()}
        )

    def record_outcome(
        self,
        tool_call: ToolCall | dict,
        result_text: str,
        artifact_id: str | None,
        run_id: str,
        goal_id: str | None = None
    ) -> MemoryItem:
        """
        Record the outcome of an MCP tool dispatch.

        Stores the result of a tool call with metadata about what was called,
        what arguments were provided, and what the result was.

        Args:
            tool_call: ToolCall object or dict with 'name' and 'arguments'
            result_text: The text result returned by the tool
            artifact_id: Optional reference to a stored artifact
            run_id: Unique identifier for the current agent run
            goal_id: Optional identifier for the associated goal

        Returns:
            The created MemoryItem
        """
        # Extract tool name and arguments
        if isinstance(tool_call, dict):
            tool_name = tool_call.get("name", "unknown")
            tool_args = tool_call.get("arguments", {})
        else:
            tool_name = tool_call.name
            tool_args = tool_call.arguments

        # Create keywords from tool name and result
        keywords = [tool_name]

        # Add argument values as keywords if they're strings
        for key, value in tool_args.items():
            if isinstance(value, str) and len(value) < 50:
                keywords.append(value.lower())

        # Add tokens from result text
        result_tokens = result_text.lower().split()[:5]  # First 5 words
        keywords.extend(result_tokens)

        # Create descriptor
        args_str = ", ".join(f"{k}={v}" for k, v in list(tool_args.items())[:3])
        descriptor = f"{tool_name}({args_str[:50]})"
        if len(args_str) > 50:
            descriptor += "..."

        # Generate unique ID
        content_hash = hashlib.sha256(
            f"{tool_name}{str(tool_args)}{result_text}{run_id}{datetime.now().isoformat()}".encode()
        ).hexdigest()
        item_id = f"out:{content_hash[:12]}"

        # Create the memory item
        item = MemoryItem(
            id=item_id,
            kind="tool_outcome",
            keywords=keywords[:10],  # Limit to 10 keywords
            descriptor=descriptor,
            value={
                "tool_name": tool_name,
                "arguments": tool_args,
                "result": result_text,
                "timestamp": datetime.now().isoformat()
            },
            artifact_id=artifact_id,
            source=f"mcp_tool:{tool_name}",
            run_id=run_id,
            goal_id=goal_id,
            confidence=0.95,  # High confidence for actual tool results
            created_at=datetime.now()
        )

        # Add to storage
        self.add(item)

        return item
