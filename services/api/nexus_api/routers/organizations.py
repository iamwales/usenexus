from __future__ import annotations

import uuid
from contextlib import suppress
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from nexus_core.database import get_db
from nexus_core.models.orm import Connection, Organization
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.dependencies import require_scopes
from nexus_api.errors import api_error

router = APIRouter(dependencies=[Depends(require_scopes("manage"))])

DbSession = Annotated[AsyncSession, Depends(get_db)]


class OrganizationOut(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    doc_limit: int
    query_limit_monthly: int
    created_at: datetime


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=3, max_length=100, pattern=r"^[a-z0-9-]+$")


@router.get("/organization", response_model=OrganizationOut)
async def get_organization(
    request: Request,
    db: DbSession,
) -> OrganizationOut:
    org = await _get_current_org(request, db)
    return _serialize_org(org)


@router.patch("/organization", response_model=OrganizationOut)
async def update_organization(
    body: OrganizationUpdate,
    request: Request,
    db: DbSession,
) -> OrganizationOut:
    org = await _get_current_org(request, db)

    if body.slug and body.slug != org.slug:
        existing = await db.scalar(
            select(Organization).where(
                Organization.slug == body.slug,
                Organization.id != org.id,
            )
        )
        if existing:
            raise api_error(409, "organization_slug_exists", "Organization slug is already taken")
        org.slug = body.slug

    if body.name is not None:
        org.name = body.name

    await db.flush()
    return _serialize_org(org)


@router.delete("/organization", status_code=202)
async def delete_organization(
    request: Request,
    db: DbSession,
) -> dict:
    org = await _get_current_org(request, db)
    connection_ids = list(
        (
            await db.scalars(
                select(Connection.id).where(
                    Connection.org_id == org.id,
                    Connection.status != "revoked",
                )
            )
        ).all()
    )

    from nexus_worker.tasks.cleanup import purge_connection

    org_id = str(org.id)
    for connection_id in connection_ids:
        purge_connection.delay(str(connection_id), org_id)

    await db.delete(org)
    await db.flush()

    redis = getattr(request.app.state, "redis", None)
    if redis is not None:
        for connection_id in connection_ids:
            with suppress(Exception):
                await redis.delete(f"connection_org:{connection_id}")

    return {
        "status": "deletion_scheduled",
        "connections_queued": len(connection_ids),
    }


async def _get_current_org(request: Request, db: AsyncSession) -> Organization:
    org_id = uuid.UUID(request.state.org_id)
    org = await db.scalar(
        select(Organization).where(
            Organization.id == org_id,
            Organization.deleted_at.is_(None),
        )
    )
    if not org:
        raise api_error(404, "organization_not_found", "Organization not found")
    return org


def _serialize_org(org: Organization) -> OrganizationOut:
    return OrganizationOut(
        id=str(org.id),
        name=org.name,
        slug=org.slug,
        plan=org.plan,
        doc_limit=org.doc_limit,
        query_limit_monthly=org.query_limit_monthly,
        created_at=org.created_at,
    )
