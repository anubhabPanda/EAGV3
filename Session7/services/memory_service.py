import sys
import hashlib
import json
from pathlib import Path
from datetime import datetime
from collections import Counter
from pydantic import BaseModel
from typing import Literal
import re


# Add parent directory to path to import schemas
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import MemoryItem, ToolCall, new_id
from services.vector_index import VectorIndex

# Add llm_gatewayV7 to path
gateway_path = Path(__file__).resolve().parent.parent.parent / "resources" / "llm_gatewayV7"
sys.path.insert(0, str(gateway_path))

from client import LLM


class MemoryExtraction(BaseModel):
    """Schema for LLM-extracted memory information."""
    kind: Literal["fact", "preference", "tool_outcome", "scratchpad"]
    keywords: list[str]
    descriptor: str
    value: dict


class Memory:
    def __init__(self, storage: list[MemoryItem] = None, memory_file: str | Path = None, llm: LLM = None, tracer=None):
        """
        Initialize the Memory service.

        Args:
            storage: Optional list of MemoryItem objects to initialize the memory with
            memory_file: Path to the JSON file for persistence (default: state/memory.json)
            llm: Optional LLM client instance (defaults to new LLM())
            tracer: Optional AgentTracer instance for logging
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


        # Kinds for which an embedding is computed at write time. Scratchpad items
        # are run-scoped and skip the vector path.
        self._EMBEDDABLE_KINDS = {"fact", "preference", "tool_outcome"}

        # Set up LLM client
        self.llm = llm if llm is not None else LLM()

        # Set up tracer
        self.tracer = tracer

        # Load from file if it exists, otherwise use provided storage
        if storage is not None:
            self.storage: list[MemoryItem] = storage
        else:
            self.storage = self._load_from_file()

        # Build deduplication index: raw_text -> memory_item_id
        # This makes duplicate detection O(1) instead of O(n)
        self._text_index: dict[str, str] = {}
        self._rebuild_index()

    def _tokens(self, text: str) -> set[str]:
        _STOPWORDS = {
            "the", "is", "a", "an", "of", "to", "and", "or", "in", "on", "for", "at",
            "with", "by", "from", "what", "how", "when", "where", "why", "this", "that",
            "it", "be", "as", "are", "was", "were", "i", "you", "me", "my", "your",
        }
        return {
            w for w in re.findall(r"\w+", text.lower())
            if w not in _STOPWORDS and len(w) > 2
        }

    def _keyword_search(
        self,
        query: str,
        history: list[dict],
        kinds: list[str] | None = None,
        top_k: int = 8
    ) -> list[MemoryItem]:
        """
        Perform keyword overlap search across memory items.

        Combines keywords and descriptor tokens for matching.
        Ranks results by overlap score and returns top-k.

        Args:
            query: The search query string
            history: Conversation history (list of message dicts)
            kinds: Optional list of memory kinds to filter by 
                   (e.g., ["fact", "preference", "tool_outcome", "scratchpad"])
            top_k: Number of top results to return (default: 8)

        Returns:
            List of top-k MemoryItem objects ranked by keyword overlap

        """

        # Tokenize the query into lowercase words
        query_tokens = set(self._tokens(query))
        if history:
            for h in history[-3:]:
                query_tokens |= self._tokens(json.dumps(h, default=str))

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
    
    def _persist_item(self, item: MemoryItem) -> MemoryItem:
        """Append `item` to the JSON store and, if it has an embedding, to the
        FAISS index. Returns the same item for caller convenience."""

        # RELOAD from disk before appending to avoid overwriting concurrent writes
        self.storage = self._load_from_file()

        self.storage.append(item)
        self._save_to_file()

        if item.embedding is not None and item.kind in self._EMBEDDABLE_KINDS:
            idx = self._index()
            idx.add(item.id, item.embedding)
            idx.persist()

            # Log vector index addition
            if self.tracer:
                self.tracer.vector_index_add(item.id, idx.size)

        # REBUILD the text index after reload
        self._rebuild_index()

        return item
    
    def _try_embed(self, text: str, task_type: str) -> list[float] | None:
        """Compute an embedding via the gateway. Returns None if the gateway is
        unavailable. The caller decides whether to persist a non-embedded item."""
        try:
            resp = self.llm.embed(text, task_type=task_type)
            embedding = list(resp["embedding"])

            # Log embedding computation
            if self.tracer:
                dimension = len(embedding)
                self.tracer.vector_embed(text, dimension, task_type)

            return embedding
        except Exception as e:
            print(f"[memory] embedding failed ({e!r}); item written without vector")
            return None

    def _index(self) -> VectorIndex:
        """Return a freshly-loaded FAISS index every call.

        Re-reading the index file is cheap at S7 scale and keeps the agent
        process consistent with writes made by the MCP subprocess (which runs
        `index_document` in a separate Python process and persists to the same
        disk files). On cold start (no index files on disk), the index is
        rebuilt from items already persisted in `memory.json`.
        """
        idx = VectorIndex(self.memory_file.parent)
        if idx.size == 0:
            for item in self.storage:
                if item.embedding is not None:
                    idx.add(item.id, item.embedding)
            if idx.size > 0:
                idx.persist()
        return idx    

    def _vector_search(
        self,
        query: str,
        *,
        kinds: list[str] | None,
        top_k: int,
    ) -> list[MemoryItem]:
        """
        Perform vector search using the embedding service.
        Returns top-k results filtered by kinds if specified.
        """
        qvec = self._try_embed(query, task_type="retrieval_query")
        if qvec is None:
            return []
        idx = self._index()
        if idx.size == 0:
            return []
        hits = idx.search(qvec, k=top_k * 2 if kinds else top_k)
        if not hits:
            return []

        # Calculate average similarity for logging
        avg_similarity = sum(score for _, score in hits) / len(hits) if hits else 0.0

        by_id: dict[str, MemoryItem] = {item.id: item for item in self.storage}
        out: list[MemoryItem] = []
        for item_id, _score in hits:
            item = by_id.get(item_id)
            if item is None:
                continue
            if kinds and item.kind not in kinds:
                continue
            item.confidence = _score
            out.append(item)
            if len(out) >= top_k:
                break

        # Log vector search
        if self.tracer:
            self.tracer.vector_search(query, len(out), idx.size, avg_similarity)

        return out
    
    def read(
        self,
        query: str,
        history: list[dict] = None,
        kinds: list[str] | None = None,
        top_k: int = 8
    ) -> list[MemoryItem]:
        """
        Read relevant memory items based on vector search or keyword overlap.
        Vector first, keyword as fallback when vector returns nothing.

        Performs vector search or keyword overlap matching across:
        - vectors of the value field (if numeric vectors are stored)
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
        # RELOAD from disk to see items added by MCP subprocess
        self.storage = self._load_from_file()
        self._rebuild_index()  # Rebuild text index for deduplication
        
        vec_hits = self._vector_search(query, kinds=kinds, top_k=top_k)
        if vec_hits:
            sorted_vec_hits = sorted(vec_hits, key=lambda x: x.confidence, reverse=True)
            return sorted_vec_hits

        # Fallback to keyword search
        keyword_hits = self._keyword_search(query, history, kinds=kinds, top_k=top_k)

        # Log fallback if tracer is available
        if self.tracer and not vec_hits:
            keywords = list(set([kw for hit in keyword_hits for kw in hit.keywords]))[:10]
            self.tracer.memory_read(len(keyword_hits), keywords=keywords, method="keyword", fallback=True)

        return keyword_hits
    
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
        
        item_tokens = item_keywords
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

    def add_fact(
        self,
        descriptor: str,
        *,
        value: dict | None = None,
        keywords: list[str] | None = None,
        source: str,
        run_id: str,
        goal_id: str | None = None,
    ) -> MemoryItem:
        """Direct fact write used by document-indexing tools. Skips the LLM
        classifier (kind is known) but still embeds the descriptor."""
        embedding = self._try_embed(descriptor, task_type="retrieval_document")
        
        item = MemoryItem(
            id=new_id("mem"),
            kind="fact",
            keywords=list({k.lower() for k in (keywords or list(self._tokens(descriptor))[:10])}),
            descriptor=descriptor,
            value=value or {},
            embedding=embedding,
            source=source,
            run_id=run_id,
            goal_id=goal_id,
            artifact_id=None
        )
        return self._persist_item(item)

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

    def _fallback_remember(
            self,
                raw_text: str, *, source: str, run_id: str, goal_id: str | None,
            ) -> MemoryItem:
            """Deterministic write when the classifier LLM is unavailable.
            Keyword extraction is naive (top word tokens); kind defaults to fact.
            The embedding is still attempted; if it fails the item persists without
            a vector and stays reachable through the keyword fallback."""
            toks = list(self._tokens(raw_text))[:10]
            descriptor = raw_text[:200]
            embedding = self._try_embed(descriptor, task_type="retrieval_document")

            item = MemoryItem(
                id=new_id("mem"),
                kind="fact",
                keywords=toks,
                descriptor=descriptor,
                value={"raw": raw_text},
                embedding=embedding,
                source=source,
                run_id=run_id,
                goal_id=goal_id,
            )
            return self._persist_item(item)    

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
                    provider = "g",
                    response_format={
                        "type": "json_schema",
                        "schema": schema,
                        "name": "Classification",
                        "strict": True,
                    },
                    temperature=1.0
                )
                break
            except Exception as e:
                if attempt == 2:
                    print(f"[memory.remember] classifier failed ({e!r}); falling back to fact-write")
                    self._fallback_remember(raw_text, source=source, run_id=run_id, goal_id=goal_id)
                continue


        # Parse the structured response
        if response.get("parsed"):
            extraction = MemoryExtraction.model_validate(response["parsed"])
        else:
            # Fallback: manual extraction
            extraction = self._fallback_remember(raw_text, source=source, run_id=run_id, goal_id=goal_id)

        # Ensure raw_text is in value
        if "raw_text" not in extraction.value:
            extraction.value["raw_text"] = raw_text
        if "timestamp" not in extraction.value:
            extraction.value["timestamp"] = datetime.now().isoformat()

        embedding: list[float] | None = None
        if extraction.kind in self._EMBEDDABLE_KINDS:
            embedding = self._try_embed(extraction.descriptor, task_type="retrieval_document")

        # Create the memory item using LLM-extracted fields
        item = MemoryItem(
            id=new_id("mem"),
            kind=extraction.kind,
            keywords=extraction.keywords,
            descriptor=extraction.descriptor,
            value=extraction.value,
            artifact_id=None,
            embedding=embedding,
            source=source,
            run_id=run_id,
            goal_id=goal_id,
            confidence=0.85,  # Higher confidence with LLM classification
            created_at=datetime.now()
        )

        # Log memory.remember with embedding info
        if self.tracer:
            self.tracer.memory_remember(raw_text, extraction.kind, extraction.keywords, embedded=(embedding is not None))

        return self._persist_item(item)

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
        arg_words = []
        for v in tool_call.arguments.values():
            if isinstance(v, str):
                arg_words += self._tokens(v)
            elif isinstance(v, (int, float)):
                arg_words.append(str(v))
        keywords = list({tool_call.name.lower(), *arg_words})[:10]

        descriptor = f"{tool_call.name}({json.dumps(tool_call.arguments)[:80]}) -> "
        if artifact_id:
            descriptor += f"artifact {artifact_id}"
        else:
            descriptor += result_text[:497].replace("\n", " ")

        embedding = self._try_embed(descriptor, task_type="retrieval_document")

        item = MemoryItem(
            id=new_id("mem"),
            kind="tool_outcome",
            keywords=keywords,
            descriptor=descriptor,
            value={
                "tool": tool_call.name,
                "arguments": tool_call.arguments,
                "result_preview": result_text[:400],
            },
            artifact_id=artifact_id,
            embedding=embedding,
            source="action",
            run_id=run_id,
            goal_id=goal_id,
        )
        return self._persist_item(item)