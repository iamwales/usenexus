"""
Kafka Consumer — Ingestion Service entry point.

Reads ChangeEvents from nexus.change_events topic.
Failed messages go to the DLQ after max_retries exhausted.
Graceful shutdown on SIGTERM.
"""

from __future__ import annotations

import asyncio
import json
import signal
from typing import Any

import redis.asyncio as aioredis
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from elasticsearch import AsyncElasticsearch
from nexus_core.config import get_settings
from nexus_core.logging import configure_logging, get_logger
from nexus_core.schemas.domain import ChangeEvent
from qdrant_client import AsyncQdrantClient

from nexus_ingestion.pipeline import (
    Deduplicator,
    Embedder,
    IngestionPipeline,
    UpsertWorker,
)

logger = get_logger(__name__)
settings = get_settings()

MAX_RETRIES = 3
_shutdown = asyncio.Event()


def _handle_signal(sig: signal.Signals) -> None:
    logger.info("consumer.shutdown_signal", signal=sig.name)
    _shutdown.set()


async def run_consumer() -> None:
    configure_logging()
    logger.info("consumer.starting", brokers=settings.kafka_brokers)

    # ── Build dependencies ────────────────────────────────────────────────────
    redis = aioredis.from_url(str(settings.redis_url), decode_responses=True)
    qdrant = AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
    )
    es = AsyncElasticsearch(
        settings.elasticsearch_url,
        api_key=settings.elasticsearch_api_key,
    )

    from nexus_connectors.registry import get_connector  # lazy import

    # Credential service — fetches + decrypts OAuth tokens from Postgres
    from nexus_ingestion.credentials import CredentialService

    credential_service = CredentialService()

    pipeline = IngestionPipeline(
        deduplicator=Deduplicator(redis),
        embedder=Embedder(),
        upsert_worker=UpsertWorker(qdrant, es),
        connector_registry=type("R", (), {"get_connector": staticmethod(get_connector)})(),
        credential_service=credential_service,
    )

    producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_broker_list,
        value_serializer=lambda v: json.dumps(v).encode(),
    )
    consumer = AIOKafkaConsumer(
        settings.kafka_topic_changes,
        bootstrap_servers=settings.kafka_broker_list,
        group_id=settings.kafka_consumer_group,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        max_poll_records=10,
        value_deserializer=lambda v: json.loads(v.decode()),
    )

    await producer.start()
    await consumer.start()
    logger.info("consumer.ready")

    # Register shutdown handlers
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: _handle_signal(s))

    try:
        async for msg in consumer:
            if _shutdown.is_set():
                break
            await _process_message(msg, pipeline, producer)
            await consumer.commit()
    finally:
        logger.info("consumer.stopping")
        await consumer.stop()
        await producer.stop()
        await redis.aclose()
        await qdrant.close()
        await es.close()
        logger.info("consumer.stopped")


async def _process_message(
    msg: Any,
    pipeline: IngestionPipeline,
    producer: AIOKafkaProducer,
) -> None:
    retry_count = 0
    raw = msg.value

    while retry_count <= MAX_RETRIES:
        try:
            event = ChangeEvent.model_validate(raw)
            await pipeline.process(event)
            return
        except Exception as e:
            retry_count += 1
            logger.warning(
                "consumer.process_error",
                error=str(e),
                attempt=retry_count,
                resource_id=raw.get("resource_id"),
            )
            if retry_count > MAX_RETRIES:
                # Send to DLQ
                raw["_dlq_error"] = str(e)
                raw["_dlq_attempts"] = retry_count
                await producer.send(settings.kafka_topic_dlq, raw)
                logger.error(
                    "consumer.sent_to_dlq",
                    resource_id=raw.get("resource_id"),
                )
                return
            await asyncio.sleep(2**retry_count)


if __name__ == "__main__":
    asyncio.run(run_consumer())
