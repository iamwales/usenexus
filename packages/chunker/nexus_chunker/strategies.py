"""
Chunking strategies for Nexus.

Design principles:
  - Chunkers are stateless and synchronous — pure functions over text.
  - Every chunker returns a list of (content, metadata_extra) tuples.
  - Caller (ingestion pipeline) wraps tuples into Chunk objects.
  - Token counting uses tiktoken (cl100k_base) — same tokenizer as OpenAI embeddings.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import tiktoken

_TOKENIZER = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_TOKENIZER.encode(text, disallowed_special=()))


def split_tokens(text: str, max_tokens: int, overlap: int) -> list[str]:
    """
    Split text into windows of max_tokens with overlap tokens of context.
    Returns list of text strings (decoded back from token IDs).
    """
    tokens = _TOKENIZER.encode(text, disallowed_special=())
    chunks: list[str] = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunk_tokens = tokens[start:end]
        chunks.append(_TOKENIZER.decode(chunk_tokens))
        if end == len(tokens):
            break
        start += max_tokens - overlap
    return chunks


@dataclass
class ChunkResult:
    content: str
    chunk_index: int
    token_count: int
    is_parent: bool = False
    parent_index: int | None = None  # child chunks reference their parent
    extra_metadata: dict[str, Any] = field(default_factory=dict)


class BaseChunker(ABC):
    @abstractmethod
    def chunk(self, content: str, title: str | None = None) -> list[ChunkResult]: ...


class FixedWindowChunker(BaseChunker):
    """Simple sliding window — good for messages, short content."""

    def __init__(self, max_tokens: int = 256, overlap: int = 32) -> None:
        self.max_tokens = max_tokens
        self.overlap = overlap

    def chunk(self, content: str, title: str | None = None) -> list[ChunkResult]:
        windows = split_tokens(content, self.max_tokens, self.overlap)
        return [
            ChunkResult(
                content=w,
                chunk_index=i,
                token_count=count_tokens(w),
            )
            for i, w in enumerate(windows)
        ]


class ParentChildChunker(BaseChunker):
    """
    Two-level chunking for long documents.

    Creates large parent chunks (good context for generation) and smaller
    child chunks (better precision for retrieval). At query time, child
    chunks are retrieved but parent chunks are sent to the LLM.

    This is the single highest-impact chunking strategy for long documents.
    """

    def __init__(
        self,
        parent_tokens: int = 1500,
        child_tokens: int = 400,
        overlap: int = 50,
    ) -> None:
        self.parent_tokens = parent_tokens
        self.child_tokens = child_tokens
        self.overlap = overlap

    def chunk(self, content: str, title: str | None = None) -> list[ChunkResult]:
        results: list[ChunkResult] = []
        chunk_index = 0

        parent_windows = split_tokens(content, self.parent_tokens, overlap=0)

        for parent_i, parent_text in enumerate(parent_windows):
            # Prepend title to parent for better context
            parent_content = f"{title}\n\n{parent_text}" if title else parent_text
            parent_result = ChunkResult(
                content=parent_content,
                chunk_index=chunk_index,
                token_count=count_tokens(parent_content),
                is_parent=True,
                extra_metadata={"parent_index": parent_i},
            )
            parent_chunk_index = chunk_index
            results.append(parent_result)
            chunk_index += 1

            # Split parent into child chunks
            child_windows = split_tokens(parent_text, self.child_tokens, self.overlap)
            for child_text in child_windows:
                results.append(
                    ChunkResult(
                        content=child_text,
                        chunk_index=chunk_index,
                        token_count=count_tokens(child_text),
                        is_parent=False,
                        parent_index=parent_chunk_index,
                    )
                )
                chunk_index += 1

        return results


class HeadingAwareChunker(BaseChunker):
    """
    Splits Markdown on headings — keeps sections together.
    Falls back to fixed-window within sections that are too large.
    Best for GitHub READMEs, Confluence pages, technical docs.
    """

    def __init__(self, max_tokens: int = 600, overlap: int = 32) -> None:
        self.max_tokens = max_tokens
        self.overlap = overlap
        self._heading_re = re.compile(r"^#{1,4}\s+.+", re.MULTILINE)

    def chunk(self, content: str, title: str | None = None) -> list[ChunkResult]:
        sections = self._split_on_headings(content)
        results: list[ChunkResult] = []
        chunk_index = 0

        for section_text in sections:
            if not section_text.strip():
                continue
            token_count = count_tokens(section_text)
            if token_count <= self.max_tokens:
                results.append(
                    ChunkResult(
                        content=section_text,
                        chunk_index=chunk_index,
                        token_count=token_count,
                    )
                )
                chunk_index += 1
            else:
                # Section too large — subdivide with fixed window
                for sub_text in split_tokens(section_text, self.max_tokens, self.overlap):
                    results.append(
                        ChunkResult(
                            content=sub_text,
                            chunk_index=chunk_index,
                            token_count=count_tokens(sub_text),
                        )
                    )
                    chunk_index += 1

        return results

    def _split_on_headings(self, content: str) -> list[str]:
        positions = [m.start() for m in self._heading_re.finditer(content)]
        if not positions:
            return [content]
        sections: list[str] = []
        for i, start in enumerate(positions):
            end = positions[i + 1] if i + 1 < len(positions) else len(content)
            sections.append(content[start:end])
        # Prepend any content before the first heading
        if positions[0] > 0:
            sections.insert(0, content[: positions[0]])
        return sections


class MetadataFirstChunker(BaseChunker):
    """
    For structured records (tasks, issues, events) that fit in one chunk.
    Ensures metadata fields appear at the start for better retrieval signal.
    If content exceeds max_tokens, truncates the description field.
    """

    def __init__(self, max_tokens: int = 350) -> None:
        self.max_tokens = max_tokens

    def chunk(self, content: str, title: str | None = None) -> list[ChunkResult]:
        token_count = count_tokens(content)
        if token_count <= self.max_tokens:
            return [ChunkResult(content=content, chunk_index=0, token_count=token_count)]

        # Truncate to max_tokens
        tokens = _TOKENIZER.encode(content, disallowed_special=())
        truncated = _TOKENIZER.decode(tokens[: self.max_tokens])
        return [
            ChunkResult(
                content=truncated + "\n[truncated]",
                chunk_index=0,
                token_count=self.max_tokens,
            )
        ]


class SemanticChunker(BaseChunker):
    """
    Splits on sentence boundaries while respecting max_tokens.
    Better than fixed-window for preserving complete thoughts.
    Good for Notion pages, Slack threads.
    """

    def __init__(self, max_tokens: int = 512, overlap: int = 64) -> None:
        self.max_tokens = max_tokens
        self.overlap = overlap
        self._sentence_re = re.compile(r"(?<=[.!?])\s+")

    def chunk(self, content: str, title: str | None = None) -> list[ChunkResult]:
        sentences = self._sentence_re.split(content)
        chunks: list[ChunkResult] = []
        current: list[str] = []
        current_tokens = 0
        chunk_index = 0

        for sentence in sentences:
            sentence_tokens = count_tokens(sentence)
            if current_tokens + sentence_tokens > self.max_tokens and current:
                chunk_text = " ".join(current)
                chunks.append(
                    ChunkResult(
                        content=chunk_text,
                        chunk_index=chunk_index,
                        token_count=count_tokens(chunk_text),
                    )
                )
                chunk_index += 1
                # Keep overlap: last few tokens as context
                overlap_sentences: list[str] = []
                overlap_count = 0
                for s in reversed(current):
                    t = count_tokens(s)
                    if overlap_count + t <= self.overlap:
                        overlap_sentences.insert(0, s)
                        overlap_count += t
                    else:
                        break
                current = overlap_sentences + [sentence]
                current_tokens = sum(count_tokens(s) for s in current)
            else:
                current.append(sentence)
                current_tokens += sentence_tokens

        if current:
            chunk_text = " ".join(current)
            chunks.append(
                ChunkResult(
                    content=chunk_text,
                    chunk_index=chunk_index,
                    token_count=count_tokens(chunk_text),
                )
            )

        return chunks


# ── Strategy selector ─────────────────────────────────────────────────────────

_CHUNKING_STRATEGIES: dict[str, BaseChunker] = {
    "google_drive_document": ParentChildChunker(parent_tokens=1500, child_tokens=400, overlap=50),
    "google_drive_file": ParentChildChunker(parent_tokens=1500, child_tokens=400, overlap=50),
    "notion_page": SemanticChunker(max_tokens=512, overlap=64),
    "notion_database_row": MetadataFirstChunker(max_tokens=350),
    "clickup_task": MetadataFirstChunker(max_tokens=300),
    "clickup_doc": ParentChildChunker(parent_tokens=1200, child_tokens=350, overlap=50),
    "slack_message": FixedWindowChunker(max_tokens=256, overlap=32),
    "google_calendar_event": MetadataFirstChunker(max_tokens=200),
    "confluence_page": ParentChildChunker(parent_tokens=1500, child_tokens=400, overlap=50),
    "github_file": HeadingAwareChunker(max_tokens=600, overlap=32),
    "github_issue": MetadataFirstChunker(max_tokens=400),
    "github_pull_request": MetadataFirstChunker(max_tokens=400),
    "linear_issue": MetadataFirstChunker(max_tokens=350),
    "linear_document": SemanticChunker(max_tokens=512, overlap=64),
    "default": FixedWindowChunker(max_tokens=512, overlap=64),
}


def get_chunker(connector_id: str, resource_type: str) -> BaseChunker:
    key = f"{connector_id}_{resource_type}"
    return _CHUNKING_STRATEGIES.get(key, _CHUNKING_STRATEGIES["default"])
