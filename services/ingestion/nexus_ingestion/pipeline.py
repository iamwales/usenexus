"""
Ingestion Pipeline

Flow:
  ChangeEvent (Kafka)
    → Deduplicator      (idempotency check via Redis)
    → ResourceFetcher   (calls connector.fetch_resource if content missing)
    → Chunker           (connector+type aware strategy)
    → Embedder          (OpenAI text-embedding-3-large, batched)
    → Upsert Worker     (Qdrant + Elasticsearch + Postgres)
"""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from datetime import UTC, datetime

from nexus_chunker.strategies import ChunkResult, get_chunker
from nexus_core.config import get_settings
from nexus_core.database import get_db_session
from nexus_core.logging import get_logger
from nexus_core.models.orm import Document
from nexus_core.schemas.domain import (
    ChangeEvent,
    ChangeEventType,
    Chunk,
    EmbeddedChunk,
)
from openai import AsyncOpenAI

logger = get_logger(__name__)
settings = get_settings()

_openai = AsyncOpenAI(api_key=settings.openai_api_key)


# ── Deduplicator ──────────────────────────────────────────────────────────────


class Deduplicator:
    """
    Idempotency gate using Redis.
    Key: tenant_id:connector_id:resource_id:content_hash
    TTL: 24h — after that we'll re-process (handles edge cases cleanly)
    """

    def __init__(self, redis_client) -> None:  # type: ignore[type-arg]
        self._redis = redis_client
        self._ttl = 86_400  # 24 hours

    async def is_duplicate(self, event: ChangeEvent, content_hash: str) -> bool:
        key = f"dedup:{event.tenant_id}:{event.connector_id}:{event.resource_id}:{content_hash}"
        result = await self._redis.set(key, "1", nx=True, ex=self._ttl)
        return result is None  # None = key already existed = duplicate

    async def invalidate(self, tenant_id: str, connector_id: str, resource_id: str) -> None:
        """Called on DELETE events to clear dedup state."""
        pattern = f"dedup:{tenant_id}:{connector_id}:{resource_id}:*"
        keys = await self._redis.keys(pattern)
        if keys:
            await self._redis.delete(*keys)


# ── Embedder ──────────────────────────────────────────────────────────────────


class Embedder:
    """Batch embed chunks using OpenAI text-embedding-3-large."""

    def __init__(self) -> None:
        self._model = settings.embedding_model
        self._batch_size = settings.embedding_batch_size
        self._dimensions = settings.embedding_dimensions

    async def embed_chunks(self, chunks: list[Chunk]) -> list[EmbeddedChunk]:
        if not chunks:
            return []

        embedded: list[EmbeddedChunk] = []
        # Process in batches
        for batch_start in range(0, len(chunks), self._batch_size):
            batch = chunks[batch_start : batch_start + self._batch_size]
            texts = [c.content for c in batch]

            try:
                response = await _openai.embeddings.create(
                    model=self._model,
                    input=texts,
                    dimensions=self._dimensions,
                )
                for chunk, embedding_obj in zip(batch, response.data, strict=False):
                    embedded.append(
                        EmbeddedChunk(
                            **chunk.model_dump(),
                            embedding=embedding_obj.embedding,
                        )
                    )
            except Exception as e:
                logger.error(
                    "embedder.batch_failed",
                    batch_size=len(batch),
                    error=str(e),
                )
                raise

        return embedded

    async def embed_query(self, text: str) -> list[float]:
        response = await _openai.embeddings.create(
            model=self._model,
            input=[text],
            dimensions=self._dimensions,
        )
        return response.data[0].embedding


# ── Upsert Worker ─────────────────────────────────────────────────────────────


class UpsertWorker:
    """Writes embedded chunks to Qdrant + Elasticsearch + Postgres."""

    def __init__(self, qdrant_client, es_client) -> None:  # type: ignore[type-arg]
        self._qdrant = qdrant_client
        self._es = es_client

    async def upsert_chunks(
        self,
        embedded_chunks: list[EmbeddedChunk],
        tenant_id: str,
    ) -> None:
        if not embedded_chunks:
            return

        await asyncio.gather(
            self._upsert_qdrant(embedded_chunks, tenant_id),
            self._upsert_elasticsearch(embedded_chunks, tenant_id),
        )

    async def delete_resource(
        self,
        tenant_id: str,
        connector_id: str,
        resource_id: str,
    ) -> None:
        """Remove all chunks for a deleted resource from both stores."""
        collection = f"{settings.qdrant_collection_prefix}_{tenant_id}"
        es_index = f"{settings.elasticsearch_index_prefix}_{tenant_id}"

        # Qdrant: delete by payload filter
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        await self._qdrant.delete(
            collection_name=collection,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="connector_id",
                        match=MatchValue(value=connector_id),
                    ),
                    FieldCondition(
                        key="resource_id",
                        match=MatchValue(value=resource_id),
                    ),
                ]
            ),
        )

        # Elasticsearch: delete by query
        await self._es.delete_by_query(
            index=es_index,
            body={
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"connector_id": connector_id}},
                            {"term": {"resource_id": resource_id}},
                        ]
                    }
                }
            },
        )
        logger.info(
            "upsert.resource_deleted",
            tenant_id=tenant_id,
            connector_id=connector_id,
            resource_id=resource_id,
        )

    async def _upsert_qdrant(
        self,
        chunks: list[EmbeddedChunk],
        tenant_id: str,
    ) -> None:
        from qdrant_client.models import PointStruct

        collection = f"{settings.qdrant_collection_prefix}_{tenant_id}"
        await self._ensure_collection(collection)

        points = [
            PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk.chunk_id)),
                vector=chunk.embedding,
                payload={
                    "chunk_id": chunk.chunk_id,
                    "tenant_id": chunk.tenant_id,
                    "connector_id": chunk.connector_id,
                    "connection_id": chunk.connection_id,
                    "resource_id": chunk.resource_id,
                    "resource_type": chunk.resource_type,
                    "chunk_index": chunk.chunk_index,
                    "parent_chunk_id": chunk.parent_chunk_id,
                    "title": chunk.title,
                    "content": chunk.content,
                    "content_preview": chunk.content_preview,
                    "source_url": chunk.source_url,
                    "author_email": chunk.author_email,
                    "created_at": chunk.created_at.isoformat() if chunk.created_at else None,
                    "modified_at": chunk.modified_at.isoformat() if chunk.modified_at else None,
                    "acl": chunk.acl,
                    "connector_metadata": chunk.connector_metadata,
                    "token_count": chunk.token_count,
                },
            )
            for chunk in chunks
        ]

        await self._qdrant.upsert(collection_name=collection, points=points)
        logger.debug("upsert.qdrant_ok", count=len(points), tenant_id=tenant_id)

    async def _upsert_elasticsearch(
        self,
        chunks: list[EmbeddedChunk],
        tenant_id: str,
    ) -> None:
        es_index = f"{settings.elasticsearch_index_prefix}_{tenant_id}"
        await self._ensure_es_index(es_index)

        ops: list[dict] = []
        for chunk in chunks:
            ops.append({"index": {"_index": es_index, "_id": chunk.chunk_id}})
            ops.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "tenant_id": chunk.tenant_id,
                    "connector_id": chunk.connector_id,
                    "resource_id": chunk.resource_id,
                    "resource_type": chunk.resource_type,
                    "chunk_index": chunk.chunk_index,
                    "parent_chunk_id": chunk.parent_chunk_id,
                    "title": chunk.title,
                    "content": chunk.content,
                    "content_preview": chunk.content_preview,
                    "source_url": chunk.source_url,
                    "author_email": chunk.author_email,
                    "modified_at": chunk.modified_at.isoformat() if chunk.modified_at else None,
                    "acl": chunk.acl,
                }
            )

        if ops:
            await self._es.bulk(body=ops, refresh=False)
            logger.debug("upsert.es_ok", count=len(chunks), tenant_id=tenant_id)

    async def _ensure_collection(self, collection: str) -> None:
        from qdrant_client.models import Distance, VectorParams

        exists = await self._qdrant.collection_exists(collection)
        if not exists:
            await self._qdrant.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(
                    size=settings.embedding_dimensions,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("upsert.collection_created", collection=collection)

    async def _ensure_es_index(self, index: str) -> None:
        exists = await self._es.indices.exists(index=index)
        if not exists:
            await self._es.indices.create(
                index=index,
                body={
                    "mappings": {
                        "properties": {
                            "content": {"type": "text", "analyzer": "english"},
                            "title": {"type": "text", "analyzer": "english"},
                            "connector_id": {"type": "keyword"},
                            "resource_id": {"type": "keyword"},
                            "tenant_id": {"type": "keyword"},
                            "acl": {"type": "keyword"},
                            "modified_at": {"type": "date"},
                        }
                    },
                    "settings": {
                        "number_of_shards": 1,
                        "number_of_replicas": 1,
                    },
                },
            )
            logger.info("upsert.es_index_created", index=index)


# ── Pipeline Orchestrator ─────────────────────────────────────────────────────


class IngestionPipeline:
    """
    Orchestrates the full ingestion flow for a single ChangeEvent.
    Called by the Kafka consumer for each message.
    """

    def __init__(
        self,
        deduplicator: Deduplicator,
        embedder: Embedder,
        upsert_worker: UpsertWorker,
        connector_registry,  # type: ignore[type-arg]
        credential_service,  # type: ignore[type-arg]
    ) -> None:
        self._dedup = deduplicator
        self._embedder = embedder
        self._upsert = upsert_worker
        self._connectors = connector_registry
        self._creds = credential_service

    async def process(self, event: ChangeEvent) -> None:
        start = time.monotonic()

        # ── Handle deletes ────────────────────────────────────────────────────
        if event.event_type == ChangeEventType.DELETED:
            await self._upsert.delete_resource(
                event.tenant_id,
                event.connector_id,
                event.resource_id,
            )
            await self._dedup.invalidate(event.tenant_id, event.connector_id, event.resource_id)
            await self._update_doc_status(event, "deleted")
            return

        # ── Resolve resource content ──────────────────────────────────────────
        resource = event.resource
        if resource is None:
            # Webhook events often omit content — fetch it
            credentials = await self._creds.get(event.connection_id)
            connector = self._connectors.get_connector(event.connector_id)
            try:
                resource = await connector.fetch_resource_with_retry(credentials, event.resource_id)
            except Exception as e:
                logger.error(
                    "pipeline.fetch_failed",
                    connector=event.connector_id,
                    resource_id=event.resource_id,
                    error=str(e),
                )
                await self._update_doc_status(event, "error", str(e))
                return

        # ── Dedup check ───────────────────────────────────────────────────────
        content_hash = hashlib.sha256(resource.content.encode()).hexdigest()
        if await self._dedup.is_duplicate(event, content_hash):
            logger.debug(
                "pipeline.duplicate_skipped",
                resource_id=event.resource_id,
            )
            return

        # ── Chunk ─────────────────────────────────────────────────────────────
        chunker = get_chunker(event.connector_id, resource.resource_type)
        chunk_results: list[ChunkResult] = chunker.chunk(resource.content, title=resource.title)

        # Build parent_chunk_id lookup — chunk_index → chunk_id
        chunk_id_map: dict[int, str] = {}
        chunks: list[Chunk] = []
        for result in chunk_results:
            chunk_id = str(uuid.uuid4())
            chunk_id_map[result.chunk_index] = chunk_id
            parent_chunk_id = (
                chunk_id_map.get(result.parent_index) if result.parent_index is not None else None
            )
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    tenant_id=event.tenant_id,
                    connector_id=event.connector_id,
                    connection_id=event.connection_id,
                    resource_id=resource.resource_id,
                    resource_type=resource.resource_type,
                    chunk_index=result.chunk_index,
                    parent_chunk_id=parent_chunk_id,
                    content=result.content,
                    title=resource.title,
                    source_url=resource.source_url,
                    author_email=resource.author_email,
                    created_at=resource.created_at,
                    modified_at=resource.modified_at,
                    acl=resource.acl,
                    connector_metadata={
                        **resource.connector_metadata,
                        **result.extra_metadata,
                        "is_parent": result.is_parent,
                    },
                    token_count=result.token_count,
                )
            )

        # ── Embed ─────────────────────────────────────────────────────────────
        embedded = await self._embedder.embed_chunks(chunks)

        # ── Upsert ────────────────────────────────────────────────────────────
        await self._upsert.upsert_chunks(embedded, event.tenant_id)

        # ── Update Postgres document record ───────────────────────────────────
        await self._update_doc_record(event, resource, content_hash, len(chunks))

        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "pipeline.processed",
            connector=event.connector_id,
            resource_id=event.resource_id,
            chunks=len(chunks),
            latency_ms=elapsed_ms,
        )

    async def _update_doc_record(
        self,
        event: ChangeEvent,
        resource,  # type: ignore[type-arg]
        content_hash: str,
        chunk_count: int,
    ) -> None:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        async with get_db_session() as session:
            stmt = (
                pg_insert(Document)
                .values(
                    org_id=uuid.UUID(event.tenant_id),
                    connection_id=uuid.UUID(event.connection_id),
                    external_id=event.resource_id,
                    resource_type=resource.resource_type,
                    title=resource.title,
                    source_url=resource.source_url,
                    content_hash=content_hash,
                    chunk_count=chunk_count,
                    indexed_at=datetime.now(tz=UTC),
                    modified_at=resource.modified_at,
                    acl=resource.acl,
                    status="indexed",
                    connector_metadata=resource.connector_metadata,
                )
                .on_conflict_do_update(
                    index_elements=["org_id", "connection_id", "external_id"],
                    set_={
                        "title": resource.title,
                        "content_hash": content_hash,
                        "chunk_count": chunk_count,
                        "indexed_at": datetime.now(tz=UTC),
                        "modified_at": resource.modified_at,
                        "acl": resource.acl,
                        "status": "indexed",
                        "error": None,
                    },
                )
            )
            await session.execute(stmt)

    async def _update_doc_status(
        self,
        event: ChangeEvent,
        status: str,
        error: str | None = None,
    ) -> None:
        from sqlalchemy import update

        async with get_db_session() as session:
            await session.execute(
                update(Document)
                .where(
                    Document.connection_id == uuid.UUID(event.connection_id),
                    Document.external_id == event.resource_id,
                )
                .values(status=status, error=error)
            )
