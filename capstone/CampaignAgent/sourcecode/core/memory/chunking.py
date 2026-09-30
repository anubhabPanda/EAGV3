"""Rohan's semantic chunking V2, hardened for the memory store.

The original EAG V1 Session 8 insight is the algorithm: give an LLM a
512-word block; if a second topic begins inside it, ask for only that suffix,
finalize the first topic, and roll the exact suffix into the next block.  This
avoids pairwise sentence calls and wastes no overlap tokens. Embeddings happen
*after* these boundaries have been chosen.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Protocol
from urllib.request import Request, urlopen

from .embeddings import Embedder


@dataclass(frozen=True)
class DocumentChunk:
    text: str
    heading: str | None
    ordinal: int
    previous_ordinal: int | None
    next_ordinal: int | None
    # The boundary is evidence, not an invisible implementation detail.  A
    # caller can distinguish a real local-LLM decision from an intentional
    # short-block pass-through or a safe failure fallback.
    segmentation: dict[str, object]
    source_start_char: int
    source_end_char: int
    source_start_word: int
    source_end_word: int


def prepare_markdown(markdown: str) -> tuple[str, str]:
    """Remove a known document wrapper without pretending it is content.

    The Session 7 paper corpus contains saved arXiv abstract *pages*, not full
    papers.  Their useful region begins at the paper-title heading and ends
    before submission history. Other Markdown passes through unchanged.
    """
    abstract_at = markdown.find("> Abstract:")
    history_at = markdown.find("## Submission history")
    if abstract_at >= 0 and history_at > abstract_at:
        headings = list(re.finditer(r"(?m)^#\s+Title:.*$", markdown[:abstract_at]))
        if headings:
            end = history_at
            for marker in ("\n| Comments:", "\n| Subjects:"):
                found = markdown.find(marker, abstract_at, history_at)
                if found >= 0:
                    end = min(end, found)
            return markdown[headings[-1].start():end].strip(), "arxiv_abstract_page"
    return markdown, "none"


class TopicSegmenter(Protocol):
    def second_topic(self, block: str) -> str: ...


class OllamaTopicSegmenter:
    """The local LLM boundary decision from Rohan's V2 implementation."""

    def __init__(self, model: str | None = None, base_url: str = "http://localhost:11434") -> None:
        self.model = model or os.getenv("S17_CHUNK_MODEL", "phi4:latest")
        self.base_url = base_url.rstrip("/")

    def second_topic(self, block: str) -> str:
        prompt = f'''You are a markdown document segmenter.

Here is a portion of a markdown document:

---
{block}
---

If this block clearly contains more than one distinct broad topic or section, reply ONLY with the exact second part copied from the block, starting from the first sentence or heading of the new topic.

Do NOT split examples, experiments, evidence, results, conclusions, or supporting details that still discuss the same main subject. A new topic should be different enough that a reader would use a different search query to retrieve it.

If it is only one topic, reply with NOTHING.

Keep markdown formatting intact. Do not add fences, labels, or explanation.'''
        body = json.dumps({"model": self.model, "messages": [{"role": "user", "content": prompt}],
                           "stream": False, "options": {"temperature": 0, "num_predict": 4096}}).encode()
        request = Request(self.base_url + "/api/chat", data=body, headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=180) as response:  # nosec B310: local configurable service
            return str(json.load(response).get("message", {}).get("content", "")).strip()

    def release(self) -> None:
        body = json.dumps({"model": self.model, "keep_alive": 0}).encode()
        request = Request(self.base_url + "/api/generate", data=body, headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=10):  # nosec B310: local configurable service
                pass
        except Exception:
            pass


class HeadingTopicSegmenter:
    """Offline/test fallback: Markdown's second heading is an explicit topic shift."""

    def second_topic(self, block: str) -> str:
        headings = list(re.finditer(r"(?m)^#{1,6}\s+.+$", block))
        return block[headings[1].start():].strip() if len(headings) > 1 else ""


def _take_words(text: str, limit: int) -> tuple[str, str]:
    """Take up to limit words while retaining the original Markdown bytes."""
    matches = list(re.finditer(r"\S+", text))
    if len(matches) <= limit:
        return text.strip(), ""
    split_at = matches[limit].start()
    return text[:split_at].rstrip(), text[split_at:].lstrip()


def _heading(chunk: str) -> str | None:
    match = re.search(r"(?m)^#{1,6}\s+(.+)$", chunk)
    return match.group(1).strip() if match else None


def _word_number(source: str, char_offset: int) -> int:
    return len(re.findall(r"\S+", source[:char_offset]))


def _structural_end(source: str, start: int, nominal_end: int) -> int:
    """Avoid cutting Markdown's indivisible structures at a word budget.

    V2 still decides topical boundaries inside the returned block.  This only
    prevents the budget cutter from opening a fence/table/heading fragment.
    """
    candidate = source[start:nominal_end]
    headings = list(re.finditer(r"(?m)^#{1,6}\s+.+$", candidate))
    if headings and headings[-1].start() > 0:
        return start + headings[-1].start()
    fences = [match.start() for match in re.finditer(r"(?m)^```", candidate)]
    if len(fences) % 2 and fences[-1] > 0:
        return start + fences[-1]
    line_start = source.rfind("\n", start, nominal_end) + 1
    if source[line_start:nominal_end].lstrip().startswith("|"):
        table_start = line_start
        while table_start > start:
            previous = source.rfind("\n", start, table_start - 1) + 1
            if not source[previous:table_start].lstrip().startswith("|"):
                break
            table_start = previous
        if table_start > start:
            return table_start
    return nominal_end


def semantic_chunks(markdown: str, embedder: Embedder, *, max_words: int = 512,
                    preprocess: bool = True, segmenter: TopicSegmenter | None = None,
                    similarity_threshold: float | None = None, min_words: int | None = 40) -> list[DocumentChunk]:
    # similarity_threshold/min_words remain accepted so S13's early prototype
    # callers fail forward; Rohan V2 deliberately uses an LLM boundary rather
    # than embedding similarity for chunk construction.
    use_live_segmenter = type(embedder).__name__ == "OllamaNomicEmbedder"
    semantic_floor = 40 if min_words is None else min_words
    del similarity_threshold, min_words, embedder
    if preprocess:
        markdown, _ = prepare_markdown(markdown)
    if not markdown.strip():
        return []
    if segmenter is None:
        live = os.getenv("S17_LIVE_SEMANTIC_CHUNKING", "1" if use_live_segmenter else "0") == "1"
        segmenter = OllamaTopicSegmenter() if live else HeadingTopicSegmenter()

    if isinstance(segmenter, OllamaTopicSegmenter):
        mode = "ollama_topic_segmenter"
        model = segmenter.model
    elif isinstance(segmenter, HeadingTopicSegmenter):
        mode = "heading_fallback"
        model = None
    else:
        mode = "injected_topic_segmenter"
        model = type(segmenter).__name__

    raw: list[tuple[str, dict[str, object], int, int]] = []
    pending_start = next((match.start() for match in re.finditer(r"\S+", markdown)), len(markdown))
    while pending_start < len(markdown):
        matches = list(re.finditer(r"\S+", markdown[pending_start:]))
        if not matches:
            break
        nominal_end = len(markdown) if len(matches) <= max_words else pending_start + matches[max_words - 1].end()
        block_end = _structural_end(markdown, pending_start, nominal_end)
        # A structural boundary immediately at the start must not stall the
        # loop; then use the ordinary word budget for this one block.
        if block_end <= pending_start:
            block_end = nominal_end
        block = markdown[pending_start:block_end].strip()
        block_start = pending_start + markdown[pending_start:block_end].find(block)
        next_start = block_end
        next_match = re.search(r"\S+", markdown[next_start:])
        remainder_start = next_start + next_match.start() if next_match else len(markdown)
        decision: dict[str, object] = {
            "mode": mode, "model": model, "block_words": len(block.split()),
        }
        if len(block.split()) < semantic_floor:
            second = ""
            decision["outcome"] = "below_semantic_floor"
        else:
            try:
                second = segmenter.second_topic(block).strip()
                decision["outcome"] = "second_topic_returned" if second else "one_topic"
            except Exception as exc:
                second = ""
                # Preserve a concise, serializable error rather than making a
                # failed semantic call indistinguishable from "one topic".
                decision["outcome"] = "segmenter_failed_fallback_to_block"
                decision["error"] = f"{type(exc).__name__}: {exc}"
        # The second topic must be a verbatim suffix. This is the no-
        # hallucination fence missing from many LLM chunkers.
        complete_suffix = bool(second) and block.rstrip().endswith(second.rstrip())
        # `second` is known to be a suffix; use its final occurrence. `find`
        # chose an earlier repeated phrase and made the wrong topic boundary.
        split_at = block.rstrip().rfind(second.rstrip()) if complete_suffix else -1
        if split_at > 0:
            first = block[:split_at].strip()
            if first:
                decision["outcome"] = "suffix_rollover"
                decision["suffix_start_char"] = split_at
                decision["suffix_words"] = len(second.split())
                first_end = block_start + split_at
                raw.append((first, decision, block_start, first_end))
            # Point back into the original Markdown. This preserves exact
            # provenance rather than rebuilding a synthetic suffix+remainder.
            pending_start = block_start + split_at
        else:
            if second and complete_suffix:
                decision["outcome"] = "suffix_at_block_start_kept_as_block"
            elif second:
                decision["outcome"] = "non_suffix_rejected_kept_as_block"
            raw.append((block, decision, block_start, block_start + len(block)))
            pending_start = remainder_start

    release = getattr(segmenter, "release", None)
    if release:
        release()

    return [DocumentChunk(text=text, heading=_heading(text), ordinal=i,
                          previous_ordinal=i - 1 if i else None,
                          next_ordinal=i + 1 if i + 1 < len(raw) else None,
                          segmentation=decision, source_start_char=start, source_end_char=end,
                          source_start_word=_word_number(markdown, start), source_end_word=_word_number(markdown, end))
            for i, (text, decision, start, end) in enumerate(raw)]


def fixed_word_chunks(text: str, *, words: int = 40) -> list[str]:
    """Baseline retained solely so the semantic-chunk proof has a control."""
    tokens = text.split()
    return [" ".join(tokens[i:i + words]) for i in range(0, len(tokens), words)]
