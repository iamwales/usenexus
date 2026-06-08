from __future__ import annotations

import asyncio
import uuid

from elasticsearch import AsyncElasticsearch
from nexus_core.config import get_settings
from nexus_core.database import get_db_session
from nexus_core.logging import configure_logging, get_logger
from nexus_core.models.orm import Document
from qdrant_client import AsyncQdrantClient

from nexus_worker.celery_app import celery_app

logger = get_logger(__name__)
settings = get_settings()


@celery_app.task(name="nexus.cleanup.purge_connection", bind=True, max_retries=3)
def purge_connection(self, connection_id: str, org_id: str) -> dict:
    configure_logging()
    try:
        return asyncio.run(_purge_connection(connection_id, org_id))
    except Exception as exc:
        logger.error("cleanup.purge_connection_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=60) from exc


async def _purge_connection(connection_id: str, org_id: str) -> dict:
    qdrant = AsyncQdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
    es = AsyncElasticsearch(settings.elasticsearch_url, api_key=settings.elasticsearch_api_key)

    collection = f"{settings.qdrant_collection_prefix}_{org_id}"
    index = f"{settings.elasticsearch_index_prefix}_{org_id}"
    try:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        if await qdrant.collection_exists(collection):
            await qdrant.delete(
                collection_name=collection,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="connection_id",
                            match=MatchValue(value=connection_id),
                        )
                    ]
                ),
            )

        if await es.indices.exists(index=index):
            await es.delete_by_query(
                index=index,
                body={"query": {"term": {"connection_id": connection_id}}},
                conflicts="proceed",
            )

        async with get_db_session() as session:
            from sqlalchemy import update

            await session.execute(
                update(Document)
                .where(Document.connection_id == uuid.UUID(connection_id))
                .values(status="deleted")
            )
    finally:
        await qdrant.close()
        await es.close()

    logger.info("cleanup.connection_purged", connection_id=connection_id, org_id=org_id)
    return {"connection_id": connection_id, "org_id": org_id}
