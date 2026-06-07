"""
Pydantic schemas used across services.
These are NOT ORM models — they are the canonical data shapes
that flow through Kafka, APIs, and inter-service calls.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ── Enums ─────────────────────────────────────────────────────────────────────


class ConnectorID(StrEnum):
    GOOGLE_DRIVE = "google_drive"
    NOTION = "notion"
    CLICKUP = "clickup"
    SLACK = "slack"
    GOOGLE_CALENDAR = "google_calendar"
    CONFLUENCE = "confluence"
    GITHUB = "github"
    LINEAR = "linear"


class ChangeEventType(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"


class ConnectionStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    REVOKED = "revoked"
    SYNCING = "syncing"


class DocumentStatus(StrEnum):
    PENDING = "pending"
    INDEXED = "indexed"
    ERROR = "error"
    DELETED = "deleted"


class SyncJobType(StrEnum):
    FULL_SYNC = "full_sync"
    INCREMENTAL = "incremental"
    SINGLE_DOC = "single_doc"


# ── OAuth ─────────────────────────────────────────────────────────────────────


class OAuthCredentials(BaseModel):
    """Decrypted OAuth credentials — NEVER log or serialize this."""

    connection_id: uuid.UUID
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


# ── Connector domain types ────────────────────────────────────────────────────


class Resource(BaseModel):
    """A single indexable item from a connector."""

    resource_id: str
    resource_type: str
    title: str | None = None
    content: str  # Extracted plain text
    source_url: str | None = None
    author_email: str | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None
    acl: list[str] = Field(default_factory=list)
    connector_metadata: dict[str, Any] = Field(default_factory=dict)


class ResourcePage(BaseModel):
    """Paginated list of resources from list_resources."""

    resources: list[Resource]
    next_cursor: str | None = None
    total_count: int | None = None


class Subscription(BaseModel):
    """Webhook subscription result."""

    subscription_id: str
    expires_at: datetime | None = None
    webhook_url: str


# ── Change events (Kafka messages) ────────────────────────────────────────────


class ChangeEvent(BaseModel):
    """
    The canonical event that flows from connector → Kafka → ingestion.
    One event per changed resource.
    """

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: ChangeEventType
    tenant_id: str  # org_id as string
    connection_id: str
    connector_id: ConnectorID
    resource_id: str
    resource_type: str
    # For CREATED/UPDATED: content to ingest. For DELETED: None.
    resource: Resource | None = None
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # Idempotency key — deduplicator uses this
    idempotency_key: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.idempotency_key:
            self.idempotency_key = f"{self.tenant_id}:{self.connector_id}:{self.resource_id}"


# ── Chunks ────────────────────────────────────────────────────────────────────


class Chunk(BaseModel):
    """A single chunk ready to be embedded and upserted."""

    chunk_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    connector_id: str
    connection_id: str
    resource_id: str
    resource_type: str
    chunk_index: int
    parent_chunk_id: str | None = None  # Set for child chunks
    content: str  # Text to embed
    content_preview: str = ""  # First 200 chars, for display
    title: str | None = None
    source_url: str | None = None
    author_email: str | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None
    acl: list[str] = Field(default_factory=list)
    connector_metadata: dict[str, Any] = Field(default_factory=dict)
    token_count: int = 0

    def model_post_init(self, __context: Any) -> None:
        if not self.content_preview:
            self.content_preview = self.content[:200]


class EmbeddedChunk(Chunk):
    """Chunk with its embedding vector attached — ready for Qdrant upsert."""

    embedding: list[float]


# ── Query / Retrieval ─────────────────────────────────────────────────────────


class RetrievedChunk(BaseModel):
    """A chunk returned from retrieval, before reranking."""

    chunk: Chunk
    score: float
    source: str = "dense"  # "dense" | "sparse"


class RankedChunk(BaseModel):
    """A chunk after RRF merge and reranking."""

    chunk: Chunk
    rrf_score: float
    rerank_score: float | None = None


class Citation(BaseModel):
    number: int
    title: str | None
    connector: str
    source_url: str | None
    excerpt: str
    author_email: str | None = None
    modified_at: datetime | None = None


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation]
    latency_ms: int
    cached: bool = False
    query_log_id: str | None = None
