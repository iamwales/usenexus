from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from nexus_core.database import get_db
from nexus_core.models.orm import ApiKey
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

DbSession = Annotated[AsyncSession, Depends(get_db)]


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    scopes: list[str] = Field(default_factory=lambda: ["query"])
    rate_limit_rpm: int = Field(default=60, ge=1, le=10_000)


class ApiKeyOut(BaseModel):
    id: str
    name: str
    key_prefix: str
    scopes: list[str]
    rate_limit_rpm: int
    last_used_at: datetime | None
    expires_at: datetime | None
    created_at: datetime


class ApiKeyCreated(ApiKeyOut):
    api_key: str


@router.get("/keys", response_model=list[ApiKeyOut])
async def list_keys(
    request: Request,
    db: DbSession,
) -> list[ApiKeyOut]:
    org_id = uuid.UUID(request.state.org_id)
    rows = (
        await db.scalars(
            select(ApiKey)
            .where(ApiKey.org_id == org_id, ApiKey.revoked_at.is_(None))
            .order_by(ApiKey.created_at.desc())
        )
    ).all()
    return [_serialize_key(row) for row in rows]


@router.post("/keys", response_model=ApiKeyCreated, status_code=201)
async def create_key(
    body: ApiKeyCreate,
    request: Request,
    db: DbSession,
) -> ApiKeyCreated:
    org_id = uuid.UUID(request.state.org_id)
    raw_key = "nxs_live_" + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:12]

    row = ApiKey(
        org_id=org_id,
        name=body.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        scopes=body.scopes,
        rate_limit_rpm=body.rate_limit_rpm,
    )
    db.add(row)
    await db.flush()

    data = _serialize_key(row).model_dump()
    return ApiKeyCreated(**data, api_key=raw_key)


@router.delete("/keys/{key_id}", status_code=204)
async def revoke_key(
    key_id: str,
    request: Request,
    db: DbSession,
) -> None:
    org_id = uuid.UUID(request.state.org_id)
    result = await db.execute(
        update(ApiKey)
        .where(ApiKey.id == uuid.UUID(key_id), ApiKey.org_id == org_id)
        .values(revoked_at=datetime.now(UTC))
    )
    if result.rowcount == 0:
        raise HTTPException(404, "API key not found")


def _serialize_key(row: ApiKey) -> ApiKeyOut:
    return ApiKeyOut(
        id=str(row.id),
        name=row.name,
        key_prefix=row.key_prefix,
        scopes=list(row.scopes or []),
        rate_limit_rpm=row.rate_limit_rpm,
        last_used_at=row.last_used_at,
        expires_at=row.expires_at,
        created_at=row.created_at,
    )
