"""
Webhooks Router — POST /v1/webhooks/{connector_id}/{connection_id}

Receives push notifications from source systems.
Validates signatures, parses ChangeEvents, publishes to Kafka.
Fast path: validate + ack in <50ms, process asynchronously.
"""

from __future__ import annotations

import json
import uuid
from contextlib import suppress

from aiokafka import AIOKafkaProducer
from fastapi import APIRouter, BackgroundTasks, Request
from nexus_core.config import get_settings
from nexus_core.database import AsyncSessionLocal
from nexus_core.logging import get_logger
from nexus_core.models.orm import Connection
from sqlalchemy import select

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter()

# Module-level Kafka producer (initialized lazily)
_producer: AIOKafkaProducer | None = None
_CONNECTION_TENANT_CACHE_TTL_SECONDS = 86_400


async def get_producer() -> AIOKafkaProducer:
    global _producer
    if not _producer_is_running(_producer):
        if _producer is not None:
            with suppress(Exception):
                await _producer.stop()
        _producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_broker_list,
            value_serializer=lambda v: json.dumps(v).encode(),
            acks="all",  # Wait for all ISR replicas
            compression_type="gzip",
        )
        await _producer.start()
    return _producer


@router.post("/webhooks/{connector_id}/{connection_id}", status_code=200)
async def receive_webhook(
    connector_id: str,
    connection_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict:
    """
    Immediately ack the webhook (providers retry on non-200).
    Parse and publish to Kafka in background.
    """
    body = await request.body()
    headers = dict(request.headers)
    payload = {}

    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        payload = {"raw": body.decode(errors="replace")}

    # Add routing context that connectors need when parsing
    tenant_id = await _get_tenant_id_for_connection(connection_id, request)
    if tenant_id is None:
        logger.warning(
            "webhook.unknown_connection",
            connector=connector_id,
            connection_id=connection_id,
        )
        return {"status": "ignored", "reason": "unknown_connection"}

    payload["tenantId"] = tenant_id
    payload["connectionId"] = connection_id

    background_tasks.add_task(
        _process_webhook,
        connector_id=connector_id,
        connection_id=connection_id,
        payload=payload,
        headers=headers,
    )

    # Google Drive and others check for 200 OK immediately
    return {"status": "ok"}


async def _process_webhook(
    connector_id: str,
    connection_id: str,
    payload: dict,
    headers: dict,
) -> None:
    from nexus_connectors.registry import get_connector, is_supported

    if not is_supported(connector_id):
        logger.warning("webhook.unknown_connector", connector_id=connector_id)
        return

    connector = get_connector(connector_id)

    try:
        events = await connector.parse_webhook(payload, headers)
    except Exception as e:
        logger.error(
            "webhook.parse_failed",
            connector=connector_id,
            connection_id=connection_id,
            error=str(e),
        )
        return

    if not events:
        logger.debug("webhook.no_events", connector=connector_id)
        return

    producer = await get_producer()
    published = 0
    for event in events:
        try:
            await producer.send(
                settings.kafka_topic_changes,
                value=event.model_dump(mode="json"),
                key=f"{event.tenant_id}:{event.resource_id}".encode(),
            )
            published += 1
        except Exception as e:
            logger.error(
                "webhook.kafka_publish_failed",
                connector=connector_id,
                error=str(e),
            )

    logger.info(
        "webhook.published",
        connector=connector_id,
        events=len(events),
        published=published,
    )


def _producer_is_running(producer: AIOKafkaProducer | None) -> bool:
    if producer is None:
        return False

    sender = getattr(producer, "_sender", None)
    sender_task = getattr(sender, "sender_task", None)
    if sender_task is None:
        return False

    task_done = getattr(sender_task, "done", None)
    return not task_done() if callable(task_done) else True


async def _get_tenant_id_for_connection(connection_id: str, request: Request) -> str | None:
    """
    Look up the org_id for a connection from Redis, falling back to Postgres.
    Webhooks are unauthenticated by user token, so they need this connection
    mapping to produce valid ChangeEvents for ingestion.
    """
    cache_key = f"connection_org:{connection_id}"
    redis = getattr(request.app.state, "redis", None)

    if redis is not None:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return cached.decode() if isinstance(cached, bytes) else str(cached)
        except Exception as e:
            logger.warning(
                "webhook.connection_cache_read_failed",
                connection_id=connection_id,
                error=str(e),
            )

    try:
        connection_uuid = uuid.UUID(connection_id)
    except ValueError:
        logger.warning("webhook.invalid_connection_id", connection_id=connection_id)
        return None

    async with AsyncSessionLocal() as session:
        tenant_id = await session.scalar(
            select(Connection.org_id).where(Connection.id == connection_uuid)
        )

    if tenant_id is None:
        return None

    tenant_id_str = str(tenant_id)
    if redis is not None:
        try:
            await redis.set(
                cache_key,
                tenant_id_str,
                ex=_CONNECTION_TENANT_CACHE_TTL_SECONDS,
            )
        except Exception as e:
            logger.warning(
                "webhook.connection_cache_write_failed",
                connection_id=connection_id,
                error=str(e),
            )

    return tenant_id_str
