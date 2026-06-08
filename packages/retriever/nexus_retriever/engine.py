"""
QueryEngine — orchestrates the full query pipeline.

Flow:
  query
    → cache check
    → HyDE expansion
    → multi-query variants
    → embed all queries
    → hybrid retrieve (Qdrant + ES, parallel)
    → permission filter
    → Cohere rerank
    → parent chunk fetch
    → context assembly
    → LLM generation
    → cache store
    → QueryResponse
"""

from __future__ import annotations

import hashlib
import json
import time

import redis.asyncio as aioredis
from elasticsearch import AsyncElasticsearch
from nexus_core.config import get_settings
from nexus_core.logging import get_logger
from nexus_core.schemas.domain import QueryResponse
from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient

from nexus_retriever.generator import Generator
from nexus_retriever.hybrid import HybridRetriever, RetrievalFilter
from nexus_retriever.hyde import HyDEExpander
from nexus_retriever.reranker import (
    CohereReranker,
    ContextAssembler,
    ParentFetcher,
    PermissionFilter,
)

logger = get_logger(__name__)
settings = get_settings()

_openai = AsyncOpenAI(api_key=settings.openai_api_key)

_MULTI_QUERY_SYSTEM = """\
Generate {n} different phrasings of the following question to improve search recall.
Return ONLY the rephrased questions, one per line, no numbering, no explanation.
Original: {query}"""


class QueryEngine:
    def __init__(
        self,
        qdrant: AsyncQdrantClient,
        es: AsyncElasticsearch,
        redis: aioredis.Redis,
    ) -> None:
        self._retriever = HybridRetriever(qdrant, es)
        self._hyde = HyDEExpander()
        self._reranker = CohereReranker()
        self._permission_filter = PermissionFilter()
        self._parent_fetcher = ParentFetcher(qdrant)
        self._assembler = ContextAssembler()
        self._generator = Generator()
        self._redis = redis
        self._qdrant = qdrant

    async def query(
        self,
        query: str,
        tenant_id: str,
        connector_ids: list[str] | None = None,
        user_email: str | None = None,
        top_k: int = 5,
        stream: bool = False,
        company_name: str = "your company",
    ) -> QueryResponse:
        start = time.monotonic()

        # ── Cache check ───────────────────────────────────────────────────────
        cache_key = self._cache_key(query, tenant_id, connector_ids, user_email)
        if not stream:
            cached = await self._get_cached(cache_key)
            if cached:
                cached.cached = True
                return cached

        # ── Query expansion ───────────────────────────────────────────────────
        query_variants = [query]
        embedding_texts = [query]

        if settings.hyde_enabled:
            hypothesis = await self._hyde.expand(query)
            embedding_texts.append(hypothesis)

        if settings.multi_query_enabled:
            variants = await self._multi_query_expand(query, n=2)
            query_variants.extend(variants)

        # ── Embed all query variants ──────────────────────────────────────────
        embeddings = await self._embed_texts(embedding_texts)

        # ── Retrieve ──────────────────────────────────────────────────────────
        retrieval_filter = RetrievalFilter(
            tenant_id=tenant_id,
            connector_ids=connector_ids,
            acl_emails=[user_email] if user_email else None,
        )
        ranked_chunks = await self._retriever.retrieve(
            query_embeddings=embeddings,
            query_texts=query_variants,
            retrieval_filter=retrieval_filter,
            top_k=settings.retrieval_top_k,
        )

        if not ranked_chunks:
            return QueryResponse(
                answer="I don't have information on that in your connected sources.",
                citations=[],
                latency_ms=int((time.monotonic() - start) * 1000),
            )

        # ── Permission filter ─────────────────────────────────────────────────
        ranked_chunks = self._permission_filter.filter(ranked_chunks, user_email)

        # ── Rerank ────────────────────────────────────────────────────────────
        ranked_chunks = await self._reranker.rerank(
            query=query,
            chunks=ranked_chunks,
            top_n=settings.rerank_top_k,
        )

        # ── Fetch parent chunks ───────────────────────────────────────────────
        ranked_chunks = await self._parent_fetcher.fetch_parents(ranked_chunks, tenant_id)
        ranked_chunks = ranked_chunks[:top_k]

        # ── Assemble context ──────────────────────────────────────────────────
        context, citation_metadata = self._assembler.assemble(ranked_chunks)

        # ── Generate ──────────────────────────────────────────────────────────
        response = await self._generator.generate(
            query=query,
            context=context,
            citation_metadata=citation_metadata,
            company_name=company_name,
        )
        response.latency_ms = int((time.monotonic() - start) * 1000)

        logger.info(
            "query.completed",
            tenant_id=tenant_id,
            latency_ms=response.latency_ms,
            sources=len(response.citations),
            chunks_retrieved=len(ranked_chunks),
        )

        # ── Cache store ───────────────────────────────────────────────────────
        if not stream:
            await self._set_cached(cache_key, response)

        return response

    async def query_stream(
        self,
        query: str,
        tenant_id: str,
        connector_ids: list[str] | None = None,
        user_email: str | None = None,
        top_k: int = 5,
        company_name: str = "your company",
    ):
        """Async generator for SSE streaming."""
        start = time.monotonic()

        if settings.hyde_enabled:
            hypothesis = await self._hyde.expand(query)
            embedding_texts = [query, hypothesis]
        else:
            embedding_texts = [query]

        embeddings = await self._embed_texts(embedding_texts)
        retrieval_filter = RetrievalFilter(
            tenant_id=tenant_id,
            connector_ids=connector_ids,
            acl_emails=[user_email] if user_email else None,
        )
        ranked_chunks = await self._retriever.retrieve(
            query_embeddings=embeddings,
            query_texts=[query],
            retrieval_filter=retrieval_filter,
            top_k=settings.retrieval_top_k,
        )
        ranked_chunks = self._permission_filter.filter(ranked_chunks, user_email)
        ranked_chunks = await self._reranker.rerank(query, ranked_chunks, top_n=top_k)
        ranked_chunks = await self._parent_fetcher.fetch_parents(ranked_chunks, tenant_id)
        ranked_chunks = ranked_chunks[:top_k]

        context, citation_metadata = self._assembler.assemble(ranked_chunks)

        async for event in self._generator.generate_stream(
            query=query,
            context=context,
            citation_metadata=citation_metadata,
            company_name=company_name,
        ):
            if event.get("type") == "done":
                event["latency_ms"] = int((time.monotonic() - start) * 1000)
            yield event

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        response = await _openai.embeddings.create(
            model=settings.embedding_model,
            input=texts,
            dimensions=settings.embedding_dimensions,
        )
        return [item.embedding for item in response.data]

    async def _multi_query_expand(self, query: str, n: int = 2) -> list[str]:
        try:
            from anthropic import AsyncAnthropic

            if not settings.anthropic_api_key:
                raise ValueError("No Anthropic key")
            client = AsyncAnthropic(api_key=settings.anthropic_api_key)
            msg = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=150,
                messages=[
                    {
                        "role": "user",
                        "content": _MULTI_QUERY_SYSTEM.format(n=n, query=query),
                    }
                ],
            )
            variants = [
                line.strip() for line in msg.content[0].text.strip().splitlines() if line.strip()
            ]
            return variants[:n]
        except Exception:
            return []

    def _cache_key(
        self,
        query: str,
        tenant_id: str,
        connector_ids: list[str] | None,
        user_email: str | None,
    ) -> str:
        parts = [query, tenant_id, json.dumps(sorted(connector_ids or [])), user_email or ""]
        return "qcache:" + hashlib.sha256(":".join(parts).encode()).hexdigest()

    async def _get_cached(self, key: str) -> QueryResponse | None:
        raw = await self._redis.get(key)
        if not raw:
            return None
        try:
            return QueryResponse.model_validate_json(raw)
        except Exception:
            return None

    async def _set_cached(self, key: str, response: QueryResponse) -> None:
        try:
            await self._redis.set(
                key,
                response.model_dump_json(),
                ex=settings.query_cache_ttl_seconds,
            )
        except Exception as e:
            logger.warning("query.cache_write_failed", error=str(e))
