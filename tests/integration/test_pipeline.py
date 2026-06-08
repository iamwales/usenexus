"""
Integration tests for the full ingest → query pipeline.

Requires: Docker Compose test stack running (postgres, redis, qdrant, elasticsearch).
Run with: docker compose -f docker-compose.test.yml up -d && pytest tests/integration

These tests use real infrastructure but mocked external APIs (OpenAI, Cohere).
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
import redis.asyncio as aioredis
from elasticsearch import AsyncElasticsearch
from nexus_core.schemas.domain import (
    ChangeEvent,
    ChangeEventType,
    Resource,
)
from nexus_ingestion.pipeline import (
    Deduplicator,
    Embedder,
    IngestionPipeline,
    UpsertWorker,
)
from qdrant_client import AsyncQdrantClient

# ── Test config ────────────────────────────────────────────────────────────────
QDRANT_URL = "http://localhost:6333"
ES_URL = "http://localhost:9200"
REDIS_URL = "redis://localhost:6379/15"  # Use DB 15 for tests (isolated)
TEST_TENANT = f"test_{uuid.uuid4().hex[:8]}"
TEST_CONN_ID = str(uuid.uuid4())
EMBEDDING_DIM = 8  # Small dimension for fast tests


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="session")
async def redis_client():
    client = aioredis.from_url(REDIS_URL, decode_responses=True)
    yield client
    await client.flushdb()  # Clean up test keys
    await client.aclose()


@pytest_asyncio.fixture(scope="session")
async def qdrant_client():
    client = AsyncQdrantClient(url=QDRANT_URL)
    yield client
    # Clean up test collection
    collection = f"tenant_{TEST_TENANT}"
    with suppress(Exception):
        await client.delete_collection(collection)
    await client.close()


@pytest_asyncio.fixture(scope="session")
async def es_client():
    client = AsyncElasticsearch(ES_URL)
    yield client
    # Clean up test index
    index = f"nexus_{TEST_TENANT}"
    with suppress(Exception):
        await client.indices.delete(index=index, ignore_unavailable=True)
    await client.close()


def make_fake_embedding(dim: int = EMBEDDING_DIM) -> list[float]:
    """Deterministic fake embedding for tests."""
    import hashlib

    seed = int(hashlib.md5(str(dim).encode()).hexdigest()[:8], 16)
    return [(seed * i % 100) / 100.0 for i in range(dim)]


@pytest_asyncio.fixture
async def pipeline(redis_client, qdrant_client, es_client):
    """Build a pipeline with mocked external AI calls."""
    deduplicator = Deduplicator(redis_client)

    # Mock embedder — returns fake vectors without calling OpenAI
    embedder = MagicMock(spec=Embedder)
    embedder.embed_chunks = AsyncMock(
        side_effect=lambda chunks: [
            __import__("nexus_core.schemas.domain", fromlist=["EmbeddedChunk"]).EmbeddedChunk(
                **chunk.model_dump(),
                embedding=make_fake_embedding(3072),  # Real dim for Qdrant
            )
            for chunk in chunks
        ]
    )

    upsert_worker = UpsertWorker(qdrant_client, es_client)

    # Mock connector registry + credential service
    mock_registry = MagicMock()
    mock_cred_service = MagicMock()

    pl = IngestionPipeline(
        deduplicator=deduplicator,
        embedder=embedder,
        upsert_worker=upsert_worker,
        connector_registry=mock_registry,
        credential_service=mock_cred_service,
    )
    return pl


# ── Helpers ────────────────────────────────────────────────────────────────────


def make_resource(
    resource_id: str,
    content: str,
    title: str = "Test Document",
    acl: list[str] | None = None,
) -> Resource:
    return Resource(
        resource_id=resource_id,
        resource_type="file",
        title=title,
        content=content,
        source_url=f"https://drive.google.com/file/{resource_id}",
        author_email="alice@test.com",
        created_at=datetime.now(tz=UTC),
        modified_at=datetime.now(tz=UTC),
        acl=acl or ["alice@test.com"],
        connector_metadata={"mime_type": "application/vnd.google-apps.document"},
    )


def make_event(
    resource: Resource,
    event_type: ChangeEventType = ChangeEventType.CREATED,
) -> ChangeEvent:
    return ChangeEvent(
        event_type=event_type,
        tenant_id=TEST_TENANT,
        connection_id=TEST_CONN_ID,
        connector_id="google_drive",
        resource_id=resource.resource_id,
        resource_type=resource.resource_type,
        resource=resource,
    )


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.integration
async def test_ingest_creates_chunks_in_qdrant(pipeline, qdrant_client):
    """After ingesting a document, chunks should exist in the Qdrant collection."""
    resource = make_resource(
        resource_id="doc_001",
        content="The Q3 strategy focuses on enterprise expansion. " * 20,
        title="Q3 Strategy Document",
    )
    event = make_event(resource)
    await pipeline.process(event)

    collection = f"tenant_{TEST_TENANT}"
    result = await qdrant_client.scroll(
        collection_name=collection,
        scroll_filter=__import__(
            "qdrant_client.models", fromlist=["Filter", "FieldCondition", "MatchValue"]
        ).Filter(
            must=[
                __import__(
                    "qdrant_client.models", fromlist=["FieldCondition", "MatchValue"]
                ).FieldCondition(
                    key="resource_id",
                    match=__import__("qdrant_client.models", fromlist=["MatchValue"]).MatchValue(
                        value="doc_001"
                    ),
                )
            ]
        ),
        limit=100,
        with_payload=True,
    )
    points, _ = result
    assert len(points) > 0
    assert all(p.payload.get("tenant_id") == TEST_TENANT for p in points)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_ingest_creates_docs_in_elasticsearch(pipeline, es_client):
    """After ingesting, document chunks should be searchable via BM25."""
    resource = make_resource(
        resource_id="doc_002",
        content="The design system uses a token-based approach for colors. " * 15,
        title="Design System Guidelines",
    )
    event = make_event(resource)
    await pipeline.process(event)

    # Allow ES to refresh (near-real-time)
    await asyncio.sleep(1.5)

    index = f"nexus_{TEST_TENANT}"
    resp = await es_client.search(
        index=index,
        body={"query": {"match": {"content": "design system token colors"}}},
    )
    hits = resp["hits"]["hits"]
    assert len(hits) > 0
    assert any("doc_002" in h["_source"].get("resource_id", "") for h in hits)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_delete_event_removes_chunks(pipeline, qdrant_client):
    """A DELETE ChangeEvent should remove all chunks for that resource."""
    # First ingest
    resource = make_resource(
        resource_id="doc_to_delete",
        content="This document will be deleted soon. " * 10,
    )
    await pipeline.process(make_event(resource, ChangeEventType.CREATED))

    # Verify chunks exist
    collection = f"tenant_{TEST_TENANT}"
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    scroll_filter = Filter(
        must=[FieldCondition(key="resource_id", match=MatchValue(value="doc_to_delete"))]
    )
    points_before, _ = await qdrant_client.scroll(
        collection_name=collection,
        scroll_filter=scroll_filter,
        limit=100,
    )
    assert len(points_before) > 0

    # Now delete
    delete_event = make_event(resource, ChangeEventType.DELETED)
    delete_event = delete_event.model_copy(update={"resource": None})
    await pipeline.process(delete_event)

    points_after, _ = await qdrant_client.scroll(
        collection_name=collection,
        scroll_filter=scroll_filter,
        limit=100,
    )
    assert len(points_after) == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_duplicate_ingest_is_skipped(pipeline, qdrant_client):
    """Ingesting the same content twice should not duplicate chunks."""
    resource = make_resource(
        resource_id="doc_dedup",
        content="Unique content that should only be indexed once. " * 10,
    )

    await pipeline.process(make_event(resource, ChangeEventType.CREATED))
    await pipeline.process(make_event(resource, ChangeEventType.CREATED))

    collection = f"tenant_{TEST_TENANT}"
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    points, _ = await qdrant_client.scroll(
        collection_name=collection,
        scroll_filter=Filter(
            must=[FieldCondition(key="resource_id", match=MatchValue(value="doc_dedup"))]
        ),
        limit=100,
    )
    # Count should equal a single ingest, not doubled
    single_count = len(points)

    # Third ingest with same content
    await pipeline.process(make_event(resource, ChangeEventType.UPDATED))
    points2, _ = await qdrant_client.scroll(
        collection_name=collection,
        scroll_filter=Filter(
            must=[FieldCondition(key="resource_id", match=MatchValue(value="doc_dedup"))]
        ),
        limit=100,
    )
    assert len(points2) == single_count  # No duplication


@pytest.mark.asyncio
@pytest.mark.integration
async def test_updated_content_replaces_old_chunks(pipeline, qdrant_client):
    """Re-ingesting with different content should update, not accumulate chunks."""
    resource_v1 = make_resource(
        resource_id="doc_update",
        content="Version one content about apples. " * 10,
    )
    resource_v2 = make_resource(
        resource_id="doc_update",
        content="Version two content about oranges — completely different. " * 10,
    )

    await pipeline.process(make_event(resource_v1, ChangeEventType.CREATED))
    await pipeline.process(make_event(resource_v2, ChangeEventType.UPDATED))

    collection = f"tenant_{TEST_TENANT}"
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    points, _ = await qdrant_client.scroll(
        collection_name=collection,
        scroll_filter=Filter(
            must=[FieldCondition(key="resource_id", match=MatchValue(value="doc_update"))]
        ),
        limit=100,
        with_payload=True,
    )
    # All remaining chunks should have the v2 content
    for point in points:
        assert "oranges" in point.payload.get("content", "")
        assert "apples" not in point.payload.get("content", "")
