"""
Full Sync Task — indexes all resources for a connection.

Runs as a Celery task so it doesn't block the API.
Uses pagination (list_resources cursor) to handle arbitrarily large sources.
Updates SyncJob progress in real time.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from nexus_core.config import get_settings
from nexus_core.database import get_db_session
from nexus_core.logging import configure_logging, get_logger
from nexus_core.models.orm import Connection, SyncJob
from nexus_core.schemas.domain import ChangeEvent, ChangeEventType
from sqlalchemy import select, update

from nexus_worker.celery_app import celery_app

logger = get_logger(__name__)
settings = get_settings()


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="nexus.full_sync",
)
def run_full_sync(self, connection_id: str) -> dict:
    """Celery entry point — runs the async sync in an event loop."""
    configure_logging()
    try:
        return asyncio.run(_full_sync(connection_id))
    except Exception as exc:
        logger.error("full_sync.failed", connection_id=connection_id, error=str(exc))
        raise self.retry(exc=exc) from exc


async def _full_sync(connection_id: str) -> dict:
    conn_uuid = uuid.UUID(connection_id)

    # ── Load connection + update job status ───────────────────────────────────
    async with get_db_session() as session:
        conn = await session.scalar(select(Connection).where(Connection.id == conn_uuid))
        if not conn:
            raise ValueError(f"Connection {connection_id} not found")

        job = await session.scalar(
            select(SyncJob)
            .where(
                SyncJob.connection_id == conn_uuid,
                SyncJob.status == "pending",
            )
            .order_by(SyncJob.created_at.desc())
            .limit(1)
        )
        if job:
            await session.execute(
                update(SyncJob)
                .where(SyncJob.id == job.id)
                .values(status="running", started_at=datetime.now(tz=UTC))
            )

    logger.info(
        "full_sync.started",
        connection_id=connection_id,
        connector=conn.connector_id,
        org_id=str(conn.org_id),
    )

    # ── Fetch credentials ─────────────────────────────────────────────────────
    from nexus_ingestion.credentials import CredentialService

    cred_service = CredentialService()
    credentials = await cred_service.get(connection_id)

    # ── Get connector ─────────────────────────────────────────────────────────
    from nexus_connectors.registry import get_connector

    connector = get_connector(conn.connector_id)

    # ── Build pipeline components ─────────────────────────────────────────────
    import redis.asyncio as aioredis
    from elasticsearch import AsyncElasticsearch
    from nexus_ingestion.pipeline import Deduplicator, Embedder, IngestionPipeline, UpsertWorker
    from qdrant_client import AsyncQdrantClient

    redis_client = aioredis.from_url(str(settings.redis_url), decode_responses=True)
    qdrant = AsyncQdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
    es = AsyncElasticsearch(settings.elasticsearch_url)

    pipeline = IngestionPipeline(
        deduplicator=Deduplicator(redis_client),
        embedder=Embedder(),
        upsert_worker=UpsertWorker(qdrant, es),
        connector_registry=type("R", (), {"get_connector": staticmethod(get_connector)})(),
        credential_service=cred_service,
    )

    # ── Paginate through all resources ────────────────────────────────────────
    cursor: str | None = None
    total_processed = 0
    errors = 0

    try:
        while True:
            page = await connector.list_resources_with_retry(credentials, cursor)

            # Process each resource in the page
            tasks = [
                _process_resource(pipeline, resource, conn, credentials)
                for resource in page.resources
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    errors += 1
                    logger.warning("full_sync.resource_error", error=str(result))
                else:
                    total_processed += 1

            # Update job progress
            if job:
                async with get_db_session() as session:
                    await session.execute(
                        update(SyncJob)
                        .where(SyncJob.id == job.id)
                        .values(docs_processed=total_processed)
                    )

            logger.info(
                "full_sync.page_done",
                connection_id=connection_id,
                page_size=len(page.resources),
                total=total_processed,
                cursor=cursor,
            )

            if not page.next_cursor:
                break
            cursor = page.next_cursor

    finally:
        await redis_client.aclose()
        await qdrant.close()
        await es.close()

    # ── Mark complete ─────────────────────────────────────────────────────────
    async with get_db_session() as session:
        await session.execute(
            update(Connection)
            .where(Connection.id == conn_uuid)
            .values(last_synced_at=datetime.now(tz=UTC), status="active")
        )
        if job:
            await session.execute(
                update(SyncJob)
                .where(SyncJob.id == job.id)
                .values(
                    status="done",
                    docs_processed=total_processed,
                    docs_total=total_processed,
                    completed_at=datetime.now(tz=UTC),
                )
            )

    logger.info(
        "full_sync.completed",
        connection_id=connection_id,
        total_processed=total_processed,
        errors=errors,
    )
    return {"processed": total_processed, "errors": errors}


async def _process_resource(pipeline, resource, conn, credentials) -> None:
    """Convert a Resource into a ChangeEvent and run through the pipeline."""
    event = ChangeEvent(
        event_type=ChangeEventType.CREATED,
        tenant_id=str(conn.org_id),
        connection_id=str(conn.id),
        connector_id=conn.connector_id,
        resource_id=resource.resource_id,
        resource_type=resource.resource_type,
        resource=resource,
    )
    await pipeline.process(event)
