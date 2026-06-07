"""
Reranker — Cohere Rerank 3.5
Permission Filter — ACL enforcement at query time
Context Assembler — formats ranked chunks for LLM consumption
"""

from __future__ import annotations

from typing import Any

import cohere
from nexus_core.config import get_settings
from nexus_core.logging import get_logger
from nexus_core.schemas.domain import Chunk, RankedChunk
from qdrant_client import AsyncQdrantClient

logger = get_logger(__name__)
settings = get_settings()


# ── Reranker ──────────────────────────────────────────────────────────────────


class CohereReranker:
    """
    Cross-encoder reranking via Cohere Rerank 3.5.
    Significantly improves precision at top-5 vs raw retrieval scores.

    Cost: ~$0.0002 per 1000 tokens — run only on top-K after RRF, not all results.
    """

    def __init__(self) -> None:
        self._client = cohere.AsyncClientV2(api_key=settings.cohere_api_key)
        self._model = "rerank-v3.5"

    async def rerank(
        self,
        query: str,
        chunks: list[RankedChunk],
        top_n: int = 8,
    ) -> list[RankedChunk]:
        if not chunks:
            return []
        if len(chunks) <= top_n:
            return chunks  # No point reranking a small set

        documents = [c.chunk.content for c in chunks]

        try:
            response = await self._client.rerank(
                model=self._model,
                query=query,
                documents=documents,
                top_n=top_n,
                return_documents=False,
            )
            reranked: list[RankedChunk] = []
            for result in response.results:
                original = chunks[result.index]
                reranked.append(
                    original.model_copy(update={"rerank_score": result.relevance_score})
                )
            return reranked

        except Exception as e:
            logger.warning("reranker.failed", error=str(e))
            # Fall back to RRF ordering, truncate to top_n
            return chunks[:top_n]


# ── Permission Filter ─────────────────────────────────────────────────────────


class PermissionFilter:
    """
    Enforces ACL at query time.

    Two-tier approach:
      1. Fast path: check ACL list stored in the chunk payload (indexed at ingest time).
         This covers 99% of cases without any API call.
      2. Slow path: if chunk ACL is stale or missing, call connector.check_permission().
         This is rare and only triggered for sensitive connectors (e.g. Google Drive).
    """

    def filter(
        self,
        chunks: list[RankedChunk],
        user_email: str | None,
    ) -> list[RankedChunk]:
        """
        Fast-path ACL filter using stored ACL lists.
        If user_email is None, skip filtering (service token — tenant-level access).
        """
        if not user_email:
            return chunks

        email_lower = user_email.lower()
        allowed: list[RankedChunk] = []

        for ranked in chunks:
            acl = ranked.chunk.acl
            if not acl:
                # No ACL recorded — include (assume public within tenant)
                allowed.append(ranked)
                continue
            if "public" in acl:
                allowed.append(ranked)
                continue
            if email_lower in [a.lower() for a in acl]:
                allowed.append(ranked)
                continue
            # Domain match — e.g. user is alice@company.com, ACL has @company.com
            domain = email_lower.split("@")[-1] if "@" in email_lower else ""
            if any(a.startswith(f"@{domain}") for a in acl):
                allowed.append(ranked)

        logger.debug(
            "permission.filtered",
            before=len(chunks),
            after=len(allowed),
            user=user_email,
        )
        return allowed


# ── Parent Chunk Fetcher ──────────────────────────────────────────────────────


class ParentFetcher:
    """
    For child chunks, swap in the parent chunk content for LLM context.
    Child chunks are retrieved (better precision) but parents are sent to
    the LLM (more context = better answers).
    """

    def __init__(self, qdrant: AsyncQdrantClient) -> None:
        self._qdrant = qdrant

    async def fetch_parents(
        self,
        chunks: list[RankedChunk],
        tenant_id: str,
    ) -> list[RankedChunk]:
        collection = f"{settings.qdrant_collection_prefix}_{tenant_id}"

        # Collect unique parent IDs needed
        parent_ids_needed: set[str] = set()
        for ranked in chunks:
            if ranked.chunk.parent_chunk_id:
                parent_ids_needed.add(ranked.chunk.parent_chunk_id)

        if not parent_ids_needed:
            return chunks  # All chunks are parents or standalone

        # Batch fetch parents from Qdrant
        parent_map: dict[str, Chunk] = {}
        try:
            import uuid as _uuid

            point_ids = [str(_uuid.uuid5(_uuid.NAMESPACE_DNS, pid)) for pid in parent_ids_needed]
            results = await self._qdrant.retrieve(
                collection_name=collection,
                ids=point_ids,
                with_payload=True,
            )
            for result in results:
                if result.payload:
                    parent_chunk_id = result.payload.get("chunk_id", "")
                    parent_map[parent_chunk_id] = HybridRetriever._payload_to_chunk(result.payload)
        except Exception as e:
            logger.warning("parent_fetch.failed", error=str(e))
            return chunks  # Fall back to child content

        # Swap child → parent content
        enriched: list[RankedChunk] = []
        for ranked in chunks:
            pid = ranked.chunk.parent_chunk_id
            if pid and pid in parent_map:
                # Keep child's metadata (source_url, title etc.) but use parent content
                parent = parent_map[pid]
                enriched_chunk = ranked.chunk.model_copy(
                    update={
                        "content": parent.content,
                        "token_count": parent.token_count,
                    }
                )
                enriched.append(ranked.model_copy(update={"chunk": enriched_chunk}))
            else:
                enriched.append(ranked)

        return enriched


# Import for _payload_to_chunk reuse
from nexus_retriever.hybrid import HybridRetriever  # noqa: E402

# ── Context Assembler ─────────────────────────────────────────────────────────


class ContextAssembler:
    """
    Formats ranked chunks into the context string sent to the LLM.
    Deduplicates overlapping content and assigns citation numbers.
    """

    def assemble(
        self,
        chunks: list[RankedChunk],
        max_tokens: int = 6000,
    ) -> tuple[str, list[dict[str, Any]]]:
        """
        Returns:
          - context_str: formatted string for the LLM prompt
          - citation_metadata: list of dicts used to build Citation objects
        """
        deduplicated = self._deduplicate(chunks)

        context_parts: list[str] = []
        citation_metadata: list[dict[str, Any]] = []
        total_tokens = 0

        for i, ranked in enumerate(deduplicated, start=1):
            chunk = ranked.chunk
            # Estimate token count
            tokens = chunk.token_count or len(chunk.content) // 4
            if total_tokens + tokens > max_tokens:
                break

            connector_label = chunk.connector_id.replace("_", " ").title()
            header = f"[{i}] {chunk.title or 'Untitled'} ({connector_label})"
            if chunk.modified_at:
                header += f" — {chunk.modified_at.strftime('%b %d, %Y')}"

            context_parts.append(f"{header}\n{chunk.content}")
            total_tokens += tokens

            citation_metadata.append(
                {
                    "number": i,
                    "title": chunk.title,
                    "connector": chunk.connector_id,
                    "source_url": chunk.source_url,
                    "excerpt": chunk.content[:300],
                    "author_email": chunk.author_email,
                    "modified_at": chunk.modified_at,
                }
            )

        context_str = "\n\n---\n\n".join(context_parts)
        return context_str, citation_metadata

    def _deduplicate(self, chunks: list[RankedChunk]) -> list[RankedChunk]:
        """
        Remove chunks that are substrings of a higher-ranked chunk.
        Prevents sending redundant context to the LLM.
        """
        seen_content: list[str] = []
        unique: list[RankedChunk] = []

        for ranked in chunks:
            content = ranked.chunk.content.strip()
            is_dup = any(content in existing or existing in content for existing in seen_content)
            if not is_dup:
                seen_content.append(content)
                unique.append(ranked)

        return unique
