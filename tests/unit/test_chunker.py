"""
Unit tests for chunking strategies.
These are pure Python — no I/O, no DB, no network.
"""

from nexus_chunker.strategies import (
    FixedWindowChunker,
    HeadingAwareChunker,
    MetadataFirstChunker,
    ParentChildChunker,
    SemanticChunker,
    get_chunker,
)

LONG_TEXT = " ".join([f"sentence {i} about a topic." for i in range(200)])
MARKDOWN_TEXT = """# Introduction
This is the intro section with some content about the project.

## Features
Here are the key features of the system.
It supports many connectors and provides great answers.

## Architecture
The architecture uses a multi-tier approach.
There is a vector database and a full-text search engine.
These are combined using reciprocal rank fusion.
"""


class TestFixedWindowChunker:
    def test_short_text_is_single_chunk(self):
        chunker = FixedWindowChunker(max_tokens=512)
        chunks = chunker.chunk("Hello world")
        assert len(chunks) == 1
        assert chunks[0].content == "Hello world"

    def test_long_text_splits_into_multiple(self):
        chunker = FixedWindowChunker(max_tokens=50, overlap=10)
        chunks = chunker.chunk(LONG_TEXT)
        assert len(chunks) > 1

    def test_chunk_indices_are_sequential(self):
        chunker = FixedWindowChunker(max_tokens=50, overlap=5)
        chunks = chunker.chunk(LONG_TEXT)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_token_counts_are_set(self):
        chunker = FixedWindowChunker(max_tokens=100, overlap=10)
        chunks = chunker.chunk(LONG_TEXT)
        for chunk in chunks:
            assert chunk.token_count > 0
            assert chunk.token_count <= 110  # allow small overage from overlap


class TestParentChildChunker:
    def test_produces_parents_and_children(self):
        chunker = ParentChildChunker(parent_tokens=200, child_tokens=50, overlap=10)
        chunks = chunker.chunk(LONG_TEXT)
        parents = [c for c in chunks if c.is_parent]
        children = [c for c in chunks if not c.is_parent]
        assert len(parents) >= 1
        assert len(children) > len(parents)

    def test_children_reference_parent_index(self):
        chunker = ParentChildChunker(parent_tokens=200, child_tokens=50, overlap=10)
        chunks = chunker.chunk(LONG_TEXT)
        parent_indices = {c.chunk_index for c in chunks if c.is_parent}
        for child in chunks:
            if not child.is_parent:
                assert child.parent_index in parent_indices

    def test_title_prepended_to_parents(self):
        chunker = ParentChildChunker(parent_tokens=500, child_tokens=100, overlap=10)
        chunks = chunker.chunk(LONG_TEXT, title="My Document")
        parents = [c for c in chunks if c.is_parent]
        for parent in parents:
            assert "My Document" in parent.content


class TestHeadingAwareChunker:
    def test_splits_on_headings(self):
        chunker = HeadingAwareChunker(max_tokens=512)
        chunks = chunker.chunk(MARKDOWN_TEXT)
        # Should produce one chunk per heading section
        assert len(chunks) >= 3

    def test_each_chunk_contains_heading(self):
        chunker = HeadingAwareChunker(max_tokens=512)
        chunks = chunker.chunk(MARKDOWN_TEXT)
        heading_chunks = [c for c in chunks if c.content.startswith("#")]
        assert len(heading_chunks) > 0

    def test_oversized_sections_subdivided(self):
        very_long_section = "# Big Section\n" + LONG_TEXT
        chunker = HeadingAwareChunker(max_tokens=50, overlap=10)
        chunks = chunker.chunk(very_long_section)
        # Should subdivide the oversized section
        assert len(chunks) > 1


class TestMetadataFirstChunker:
    def test_short_content_is_single_chunk(self):
        chunker = MetadataFirstChunker(max_tokens=350)
        content = "Task: Fix login bug\nStatus: In Progress\nAssignee: Alice"
        chunks = chunker.chunk(content)
        assert len(chunks) == 1

    def test_long_content_truncated_with_marker(self):
        chunker = MetadataFirstChunker(max_tokens=20)
        long_content = "word " * 200
        chunks = chunker.chunk(long_content)
        assert len(chunks) == 1
        assert "[truncated]" in chunks[0].content


class TestSemanticChunker:
    def test_produces_chunks(self):
        chunker = SemanticChunker(max_tokens=100, overlap=20)
        chunks = chunker.chunk(LONG_TEXT)
        assert len(chunks) >= 1

    def test_no_empty_chunks(self):
        chunker = SemanticChunker(max_tokens=100, overlap=20)
        chunks = chunker.chunk(LONG_TEXT)
        for chunk in chunks:
            assert chunk.content.strip()


class TestGetChunker:
    def test_known_connectors_return_correct_chunker(self):
        assert isinstance(get_chunker("google_drive", "document"), ParentChildChunker)
        assert isinstance(get_chunker("clickup", "task"), MetadataFirstChunker)
        assert isinstance(get_chunker("github", "file"), HeadingAwareChunker)
        assert isinstance(get_chunker("slack", "message"), FixedWindowChunker)

    def test_unknown_connector_returns_default(self):
        chunker = get_chunker("unknown_app", "unknown_type")
        assert isinstance(chunker, FixedWindowChunker)
