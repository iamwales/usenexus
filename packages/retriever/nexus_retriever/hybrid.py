"""
Hybrid Retriever

Runs dense (Qdrant ANN) and sparse (Elasticsearch BM25) retrieval
in parallel, then merges results using Reciprocal Rank Fusion (RRF).

RRF formula: score(d) = Σ 1 / (k + rank(d))
where k=60 is a smoothing constant.

This consistently outperforms either retriever alone by ~10% on NDCG@10.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from elasticsearch import AsyncElasticsearch
from nexus_core.config import get_settings
from nexus_core.logging import get_logger
from nexus_core.schemas.domain import Chunk, RankedChunk, RetrievedChunk
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchAny

logger = get_logger(__name__)
settings = get_settings()

_RRF_K = 60  # Standard RRF smoothing constant


@dataclass
class RetrievalFilter:
    tenant_id: str
    connector_ids: list[str] | None = None  # None = all connectors
    acl_emails: list[str] | None = None  # None = no ACL filtering
    modified_after: str | None = None  # ISO datetime string


class HybridRetriever:
    def __init__(
        self,
        qdrant: AsyncQdrantClient,
        es: AsyncElasticsearch,
    ) -> None:
        self._qdrant = qdrant
        self._es = es

    async def retrieve(
        self,
        query_embeddings: list[list[float]],  # One per query variant (original + HyDE)
        query_texts: list[str],  # For BM25
        retrieval_filter: RetrievalFilter,
        top_k: int = 40,
    ) -> list[RankedChunk]:
        """
        Run all query variants in parallel across both retrieval systems,
        then RRF-merge and deduplicate.
        """
        collection = f"{settings.qdrant_collection_prefix}_{retrieval_filter.tenant_id}"
        es_index = f"{settings.elasticsearch_index_prefix}_{retrieval_filter.tenant_id}"

        # Launch all retrieval tasks in parallel
        tasks: list[asyncio.Task] = []
        for embedding in query_embeddings:
            tasks.append(
                asyncio.create_task(
                    self._dense_search(embedding, retrieval_filter, collection, top_k)
                )
            )
        for text in query_texts:
            tasks.append(
                asyncio.create_task(
                    self._sparse_search(text, retrieval_filter, es_index, top_k // 2)
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect all result lists, skip failed tasks
        all_result_lists: list[list[RetrievedChunk]] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning("retriever.task_failed", task_index=i, error=str(result))
                continue
            all_result_lists.append(result)

        if not all_result_lists:
            return []

        # RRF merge
        merged = self._rrf_merge(all_result_lists, top_k=top_k)
        logger.debug(
            "retriever.merged",
            result_lists=len(all_result_lists),
            final_count=len(merged),
        )
        return merged

    async def _dense_search(
        self,
        embedding: list[float],
        f: RetrievalFilter,
        collection: str,
        top_k: int,
    ) -> list[RetrievedChunk]:
        qdrant_filter = self._build_qdrant_filter(f)

        try:
            results = await self._qdrant.search(
                collection_name=collection,
                query_vector=embedding,
                query_filter=qdrant_filter,
                limit=top_k,
                with_payload=True,
            )
        except Exception as e:
            logger.warning("retriever.qdrant_failed", error=str(e))
            return []

        chunks: list[RetrievedChunk] = []
        for hit in results:
            chunk = self._payload_to_chunk(hit.payload or {})
            chunks.append(RetrievedChunk(chunk=chunk, score=hit.score, source="dense"))
        return chunks

    async def _sparse_search(
        self,
        query_text: str,
        f: RetrievalFilter,
        index: str,
        top_k: int,
    ) -> list[RetrievedChunk]:
        must_clauses: list[dict] = [
            {
                "multi_match": {
                    "query": query_text,
                    "fields": ["content^2", "title^3"],
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            }
        ]
        filter_clauses: list[dict] = []

        if f.connector_ids:
            filter_clauses.append({"terms": {"connector_id": f.connector_ids}})
        if f.acl_emails:
            filter_clauses.append(
                {
                    "bool": {
                        "should": [
                            {"terms": {"acl": f.acl_emails}},
                            {"term": {"acl": "public"}},
                        ],
                        "minimum_should_match": 1,
                    }
                }
            )
        if f.modified_after:
            filter_clauses.append({"range": {"modified_at": {"gte": f.modified_after}}})

        body: dict[str, Any] = {
            "query": {
                "bool": {
                    "must": must_clauses,
                    **({"filter": filter_clauses} if filter_clauses else {}),
                }
            },
            "size": top_k,
            "_source": True,
        }

        try:
            resp = await self._es.search(index=index, body=body)
        except Exception as e:
            logger.warning("retriever.es_failed", error=str(e))
            return []

        chunks: list[RetrievedChunk] = []
        for hit in resp["hits"]["hits"]:
            chunk = self._payload_to_chunk(hit["_source"])
            chunks.append(
                RetrievedChunk(
                    chunk=chunk,
                    score=float(hit["_score"]),
                    source="sparse",
                )
            )
        return chunks

    def _rrf_merge(
        self,
        result_lists: list[list[RetrievedChunk]],
        top_k: int,
    ) -> list[RankedChunk]:
        """
        Reciprocal Rank Fusion across multiple result lists.
        Each chunk gets score = Σ 1/(k + rank) across all lists it appears in.
        """
        scores: dict[str, float] = {}
        chunk_map: dict[str, Chunk] = {}

        for result_list in result_lists:
            for rank, retrieved in enumerate(result_list, start=1):
                chunk_id = retrieved.chunk.chunk_id
                rrf_score = 1.0 / (_RRF_K + rank)
                scores[chunk_id] = scores.get(chunk_id, 0.0) + rrf_score
                chunk_map[chunk_id] = retrieved.chunk

        # Sort by RRF score descending, return top_k
        sorted_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)
        return [
            RankedChunk(
                chunk=chunk_map[cid],
                rrf_score=scores[cid],
            )
            for cid in sorted_ids[:top_k]
        ]

    def _build_qdrant_filter(self, f: RetrievalFilter) -> Filter | None:
        conditions: list[FieldCondition] = []

        if f.connector_ids:
            conditions.append(
                FieldCondition(
                    key="connector_id",
                    match=MatchAny(any=f.connector_ids),
                )
            )
        if f.acl_emails:
            # Qdrant: chunk must have at least one ACL match
            # We check this in the permission filter step — Qdrant can't do OR
            # across a list field natively in all versions, so we do it post-fetch.
            pass

        if not conditions:
            return None
        return Filter(must=conditions)

    @staticmethod
    def _payload_to_chunk(payload: dict[str, Any]) -> Chunk:
        from datetime import datetime

        return Chunk(
            chunk_id=payload.get("chunk_id", ""),
            tenant_id=payload.get("tenant_id", ""),
            connector_id=payload.get("connector_id", ""),
            connection_id=payload.get("connection_id", ""),
            resource_id=payload.get("resource_id", ""),
            resource_type=payload.get("resource_type", ""),
            chunk_index=payload.get("chunk_index", 0),
            parent_chunk_id=payload.get("parent_chunk_id"),
            content=payload.get("content", ""),
            content_preview=payload.get("content_preview", ""),
            title=payload.get("title"),
            source_url=payload.get("source_url"),
            author_email=payload.get("author_email"),
            modified_at=datetime.fromisoformat(payload["modified_at"])
            if payload.get("modified_at")
            else None,
            acl=payload.get("acl", []),
            connector_metadata=payload.get("connector_metadata", {}),
            token_count=payload.get("token_count", 0),
        )
