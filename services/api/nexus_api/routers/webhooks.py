"""
Webhooks Router — POST /v1/webhooks/{connector_id}/{connection_id}

Receives push notifications from source systems.
Validates signatures, parses ChangeEvents, publishes to Kafka.
Fast path: validate + ack in <50ms, process asynchronously.
"""

from __future__ import annotations

import json

from aiokafka import AIOKafkaProducer
from fastapi import APIRouter, BackgroundTasks, Request
from nexus_core.config import get_settings
from nexus_core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter()

# Module-level Kafka producer (initialized lazily)
_producer: AIOKafkaProducer | None = None


async def get_producer() -> AIOKafkaProducer:
    global _producer
    if _producer is None or not _producer._sender.sender_task:
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
    payload["tenantId"] = _get_tenant_id_for_connection(connection_id, request)
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


def _get_tenant_id_for_connection(connection_id: str, request: Request) -> str:
    """
    Look up the org_id for a connection from Redis cache.
    For webhooks (no auth header), we cache connection→org mapping at
    connection creation time.
    """
    # In practice: cache connection_id → org_id in Redis at creation time
    # For now return empty string — full impl uses Redis lookup
    return ""
