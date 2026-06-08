"""
Nexus API — FastAPI application factory.

Lifespan: connects to Qdrant, ES, Redis on startup; closes on shutdown.
All shared clients are stored on app.state for dependency injection.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from elasticsearch import AsyncElasticsearch
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from nexus_core.config import get_settings
from nexus_core.logging import configure_logging, get_logger
from qdrant_client import AsyncQdrantClient

from nexus_api.middleware.auth import AuthMiddleware
from nexus_api.middleware.rate_limit import RateLimitMiddleware
from nexus_api.routers import connections, documents, health, keys, query, webhooks

logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info("api.starting", environment=settings.environment)

    # ── Connect clients ───────────────────────────────────────────────────────
    app.state.redis = aioredis.from_url(str(settings.redis_url), decode_responses=True)
    app.state.qdrant = AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
    )
    app.state.es = AsyncElasticsearch(
        settings.elasticsearch_url,
        api_key=settings.elasticsearch_api_key,
    )

    # ── Run DB migrations on startup (dev/staging only) ───────────────────────
    if not settings.is_production:
        from alembic import command
        from alembic.config import Config

        alembic_cfg = Config("services/api/alembic.ini")
        command.upgrade(alembic_cfg, "head")
        logger.info("api.migrations_applied")

    logger.info("api.ready")
    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    await app.state.redis.aclose()
    await app.state.qdrant.close()
    await app.state.es.close()
    logger.info("api.stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Nexus API",
        description="Connect everything. Know everything.",
        version="1.0.0",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    # ── Middleware ────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if not settings.is_production else ["https://usenexus.ai"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(AuthMiddleware)
    app.add_middleware(RateLimitMiddleware)

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(health.router, tags=["Health"])
    app.include_router(query.router, prefix="/v1", tags=["Query"])
    app.include_router(connections.router, prefix="/v1", tags=["Connections"])
    app.include_router(documents.router, prefix="/v1", tags=["Documents"])
    app.include_router(keys.router, prefix="/v1", tags=["API Keys"])
    app.include_router(webhooks.router, prefix="/v1", tags=["Webhooks"])

    return app


app = create_app()
