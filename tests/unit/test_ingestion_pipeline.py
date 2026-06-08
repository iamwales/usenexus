"""
Focused unit tests for ingestion pipeline regression fixes.
"""

from __future__ import annotations

from nexus_core.schemas.domain import EmbeddedChunk
from nexus_ingestion.pipeline import Deduplicator, UpsertWorker


class FakeRedis:
    def __init__(self) -> None:
        self.scan_calls: list[dict] = []
        self.deleted: list[str] = []

    async def scan(self, cursor: int, match: str, count: int) -> tuple[int, list[str]]:
        self.scan_calls.append({"cursor": cursor, "match": match, "count": count})
        if cursor == 0:
            return 1, ["dedup:tenant:google_drive:doc:hash_1"]
        return 0, ["dedup:tenant:google_drive:doc:hash_2"]

    async def delete(self, *keys: str) -> None:
        self.deleted.extend(keys)

    async def keys(self, pattern: str) -> list[str]:
        raise AssertionError(f"KEYS should not be used for invalidation: {pattern}")


class FakeIndices:
    def __init__(self) -> None:
        self.created_body: dict | None = None

    async def exists(self, index: str) -> bool:
        return False

    async def create(self, index: str, body: dict) -> None:
        self.created_body = body


class FakeElasticsearch:
    def __init__(self) -> None:
        self.indices = FakeIndices()
        self.bulk_body: list[dict] | None = None

    async def bulk(self, body: list[dict], refresh: bool) -> None:
        self.bulk_body = body


def make_embedded_chunk() -> EmbeddedChunk:
    return EmbeddedChunk(
        tenant_id="tenant_1",
        connector_id="google_drive",
        connection_id="connection_1",
        resource_id="doc_1",
        resource_type="file",
        chunk_index=0,
        content="A production readiness test chunk.",
        title="Production Readiness",
        acl=["alice@example.com"],
        embedding=[0.1, 0.2, 0.3],
    )


async def test_deduplicator_invalidate_uses_scan_batches() -> None:
    redis = FakeRedis()

    await Deduplicator(redis).invalidate("tenant", "google_drive", "doc")

    assert redis.scan_calls == [
        {
            "cursor": 0,
            "match": "dedup:tenant:google_drive:doc:*",
            "count": 500,
        },
        {
            "cursor": 1,
            "match": "dedup:tenant:google_drive:doc:*",
            "count": 500,
        },
    ]
    assert redis.deleted == [
        "dedup:tenant:google_drive:doc:hash_1",
        "dedup:tenant:google_drive:doc:hash_2",
    ]


async def test_elasticsearch_docs_and_mapping_include_connection_id() -> None:
    es = FakeElasticsearch()
    worker = UpsertWorker(qdrant_client=None, es_client=es)

    await worker._upsert_elasticsearch([make_embedded_chunk()], "tenant_1")

    assert es.bulk_body is not None
    indexed_doc = es.bulk_body[1]
    assert indexed_doc["connection_id"] == "connection_1"

    assert es.indices.created_body is not None
    properties = es.indices.created_body["mappings"]["properties"]
    assert properties["connection_id"] == {"type": "keyword"}
