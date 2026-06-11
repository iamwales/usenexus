"""
Connections Router

GET    /v1/connections
GET    /v1/connections/oauth/start
GET    /v1/connections/oauth/callback
GET    /v1/connections/{id}/status
POST   /v1/connections/{id}/sync
DELETE /v1/connections/{id}
"""

from __future__ import annotations

import json
import secrets
import uuid
from contextlib import suppress
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from nexus_core.config import get_settings
from nexus_core.database import get_db
from nexus_core.logging import get_logger
from nexus_core.models.orm import Connection, SyncJob
from nexus_core.schemas.domain import ConnectionStatus
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.dependencies import require_scopes
from nexus_api.errors import api_error

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter()
_CONNECTION_TENANT_CACHE_TTL_SECONDS = 86_400

DbSession = Annotated[AsyncSession, Depends(get_db)]


class ConnectionOut(BaseModel):
    id: str
    connector_id: str
    display_name: str | None
    status: str
    last_synced_at: datetime | None
    error_message: str | None

    model_config = {"from_attributes": True}


class SyncJobOut(BaseModel):
    job_id: str
    status: str
    docs_processed: int
    docs_total: int | None


@router.get(
    "/connections",
    response_model=list[ConnectionOut],
    dependencies=[Depends(require_scopes("manage"))],
)
async def list_connections(
    request: Request,
    db: DbSession,
) -> list[ConnectionOut]:
    org_id = uuid.UUID(request.state.org_id)
    rows = await db.scalars(
        select(Connection).where(
            Connection.org_id == org_id,
            Connection.status != "revoked",
        )
    )
    return [ConnectionOut.model_validate(r) for r in rows.all()]


@router.get(
    "/connections/oauth/start",
    dependencies=[Depends(require_scopes("manage"))],
)
async def oauth_start(
    request: Request,
    db: DbSession,
    connector: str = Query(...),
) -> dict:
    from nexus_connectors.registry import get_connector, is_supported

    if not is_supported(connector):
        raise api_error(
            400,
            "unknown_connector",
            "Unknown connector",
            details={"connector": connector},
        )

    org_id = request.state.org_id
    state_token = secrets.token_urlsafe(32)
    redirect_uri = f"{settings.api_base_url}/v1/connections/oauth/callback"

    # Store state → (org_id, connector_id) in Redis (TTL 10min)
    redis = request.app.state.redis
    await redis.set(
        f"oauth_state:{state_token}",
        json.dumps({"org_id": org_id, "connector_id": connector}),
        ex=600,
    )

    connector_obj = get_connector(connector)
    oauth_url = await connector_obj.get_auth_url(
        state=state_token,
        redirect_uri=redirect_uri,
    )
    return {"oauth_url": oauth_url, "state": state_token}


@router.get("/connections/oauth/callback")
async def oauth_callback(
    request: Request,
    db: DbSession,
    code: str = Query(...),
    state: str = Query(...),
) -> dict:
    redis = request.app.state.redis
    state_raw = await redis.get(f"oauth_state:{state}")
    if not state_raw:
        raise api_error(400, "invalid_oauth_state", "Invalid or expired state token")

    state_data = json.loads(state_raw)
    org_id = uuid.UUID(state_data["org_id"])
    connector_id = state_data["connector_id"]
    await redis.delete(f"oauth_state:{state}")

    from nexus_connectors.registry import get_connector
    from nexus_ingestion.credentials import CredentialService

    connector_obj = get_connector(connector_id)
    redirect_uri = f"{settings.api_base_url}/v1/connections/oauth/callback"

    creds = await connector_obj.exchange_code(code, redirect_uri)

    # Create connection record
    connection = Connection(
        org_id=org_id,
        connector_id=connector_id,
        status=ConnectionStatus.ACTIVE,
        display_name=connector_obj.display_name,
        scopes=connector_obj.oauth_scopes,
    )
    db.add(connection)
    await db.flush()  # Get the connection.id

    # Register webhook
    webhook_url = f"{settings.api_base_url}/v1/webhooks/{connector_id}/{connection.id}"
    try:
        sub = await connector_obj.subscribe(creds, webhook_url)
        connection.webhook_sub_id = sub.subscription_id
        connection.webhook_expires_at = sub.expires_at
    except Exception as e:
        logger.warning(
            "connections.webhook_failed",
            connector=connector_id,
            error=str(e),
        )

    await db.commit()
    try:
        await redis.set(
            f"connection_org:{connection.id}",
            str(org_id),
            ex=_CONNECTION_TENANT_CACHE_TTL_SECONDS,
        )
    except Exception as e:
        logger.warning(
            "connections.tenant_cache_write_failed",
            connection_id=str(connection.id),
            error=str(e),
        )

    # Save credentials (encrypted)
    creds = creds.model_copy(update={"connection_id": connection.id})
    cred_service = CredentialService(request.app.state.redis)
    await cred_service.save(connection.id, creds, settings.encryption_key_id)

    # Trigger full sync job
    job = SyncJob(
        org_id=org_id,
        connection_id=connection.id,
        job_type="full_sync",
        status="pending",
    )
    db.add(job)
    await db.commit()

    # Enqueue via Celery
    from nexus_worker.tasks.full_sync import run_full_sync

    run_full_sync.delay(str(connection.id))

    logger.info(
        "connections.created",
        connection_id=str(connection.id),
        connector=connector_id,
        org_id=str(org_id),
    )
    return {
        "connection_id": str(connection.id),
        "connector_id": connector_id,
        "status": "active",
        "sync_job_id": str(job.id),
    }


@router.get(
    "/connections/{connection_id}/status",
    dependencies=[Depends(require_scopes("manage"))],
)
async def connection_status(
    connection_id: str,
    request: Request,
    db: DbSession,
) -> dict:
    org_id = uuid.UUID(request.state.org_id)
    conn = await _get_connection(db, connection_id, org_id)

    # Get latest sync job
    job = await db.scalar(
        select(SyncJob)
        .where(SyncJob.connection_id == conn.id)
        .order_by(SyncJob.created_at.desc())
        .limit(1)
    )

    # Get doc count
    from nexus_core.models.orm import Document
    from sqlalchemy import func

    doc_count = await db.scalar(
        select(func.count(Document.id)).where(
            Document.connection_id == conn.id,
            Document.status == "indexed",
        )
    )

    return {
        "connection_id": connection_id,
        "connector_id": conn.connector_id,
        "status": conn.status,
        "last_synced_at": conn.last_synced_at,
        "error_message": conn.error_message,
        "docs_indexed": doc_count or 0,
        "latest_sync": {
            "job_id": str(job.id) if job else None,
            "status": job.status if job else None,
            "docs_processed": job.docs_processed if job else 0,
            "docs_total": job.docs_total if job else None,
        },
    }


@router.post(
    "/connections/{connection_id}/sync",
    dependencies=[Depends(require_scopes("manage"))],
)
async def trigger_sync(
    connection_id: str,
    request: Request,
    db: DbSession,
) -> dict:
    org_id = uuid.UUID(request.state.org_id)
    conn = await _get_connection(db, connection_id, org_id)

    job = SyncJob(
        org_id=org_id,
        connection_id=conn.id,
        job_type="full_sync",
        status="pending",
    )
    db.add(job)
    await db.commit()

    from nexus_worker.tasks.full_sync import run_full_sync

    run_full_sync.delay(connection_id)

    return {"job_id": str(job.id), "status": "pending"}


@router.delete(
    "/connections/{connection_id}",
    status_code=204,
    dependencies=[Depends(require_scopes("manage"))],
)
async def delete_connection(
    connection_id: str,
    request: Request,
    db: DbSession,
) -> None:
    org_id = uuid.UUID(request.state.org_id)
    conn = await _get_connection(db, connection_id, org_id)

    # Revoke webhook
    try:
        from nexus_connectors.registry import get_connector
        from nexus_ingestion.credentials import CredentialService

        cred_service = CredentialService(request.app.state.redis)
        creds = await cred_service.get(connection_id)
        connector_obj = get_connector(conn.connector_id)
        if conn.webhook_sub_id:
            await connector_obj.unsubscribe(creds, conn.webhook_sub_id)
    except Exception as e:
        logger.warning("connections.unsubscribe_failed", error=str(e))

    # Enqueue data purge
    from nexus_worker.tasks.cleanup import purge_connection

    purge_connection.delay(connection_id, str(org_id))

    # Mark revoked
    await db.execute(update(Connection).where(Connection.id == conn.id).values(status="revoked"))
    await db.commit()
    with suppress(Exception):
        await request.app.state.redis.delete(f"connection_org:{connection_id}")


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_connection(
    db: AsyncSession,
    connection_id: str,
    org_id: uuid.UUID,
) -> Connection:
    try:
        connection_uuid = uuid.UUID(connection_id)
    except ValueError as e:
        raise api_error(400, "invalid_connection_id", "Connection id must be a valid UUID") from e

    conn = await db.scalar(
        select(Connection).where(
            Connection.id == connection_uuid,
            Connection.org_id == org_id,
        )
    )
    if not conn:
        raise api_error(404, "connection_not_found", "Connection not found")
    return conn
