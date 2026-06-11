from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from nexus_core.database import get_db
from nexus_core.models.orm import ApiKey
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.dependencies import require_scopes
from nexus_api.errors import api_error

router = APIRouter(dependencies=[Depends(require_scopes("manage"))])

DbSession = Annotated[AsyncSession, Depends(get_db)]
_ALLOWED_SCOPES = {"query", "manage"}


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    scopes: list[str] = Field(default_factory=lambda: ["query"])
    rate_limit_rpm: int = Field(default=60, ge=1, le=10_000)
    expires_at: datetime | None = None

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, scopes: list[str]) -> list[str]:
        invalid = sorted(set(scopes) - _ALLOWED_SCOPES)
        if invalid:
            raise ValueError(f"Unsupported API key scopes: {invalid}")
        return sorted(set(scopes))


class ApiKeyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    scopes: list[str] | None = None
    rate_limit_rpm: int | None = Field(default=None, ge=1, le=10_000)
    expires_at: datetime | None = None

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, scopes: list[str] | None) -> list[str] | None:
        if scopes is None:
            return scopes
        invalid = sorted(set(scopes) - _ALLOWED_SCOPES)
        if invalid:
            raise ValueError(f"Unsupported API key scopes: {invalid}")
        return sorted(set(scopes))


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
        expires_at=body.expires_at,
    )
    db.add(row)
    await db.flush()

    data = _serialize_key(row).model_dump()
    return ApiKeyCreated(**data, api_key=raw_key)


@router.patch("/keys/{key_id}", response_model=ApiKeyOut)
async def update_key(
    key_id: str,
    body: ApiKeyUpdate,
    request: Request,
    db: DbSession,
) -> ApiKeyOut:
    org_id = uuid.UUID(request.state.org_id)
    key_uuid = _parse_key_id(key_id)
    row = await db.scalar(
        select(ApiKey).where(
            ApiKey.id == key_uuid,
            ApiKey.org_id == org_id,
            ApiKey.revoked_at.is_(None),
        )
    )
    if not row:
        raise api_error(404, "api_key_not_found", "API key not found")

    if body.name is not None:
        row.name = body.name
    if body.scopes is not None:
        row.scopes = body.scopes
    if body.rate_limit_rpm is not None:
        row.rate_limit_rpm = body.rate_limit_rpm
    if "expires_at" in body.model_fields_set:
        row.expires_at = body.expires_at

    await db.flush()
    return _serialize_key(row)


@router.delete("/keys/{key_id}", status_code=204)
async def revoke_key(
    key_id: str,
    request: Request,
    db: DbSession,
) -> None:
    org_id = uuid.UUID(request.state.org_id)
    key_uuid = _parse_key_id(key_id)
    result = await db.execute(
        update(ApiKey)
        .where(ApiKey.id == key_uuid, ApiKey.org_id == org_id, ApiKey.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    if result.rowcount == 0:
        raise api_error(404, "api_key_not_found", "API key not found")


def _parse_key_id(key_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(key_id)
    except ValueError as e:
        raise api_error(400, "invalid_api_key_id", "API key id must be a valid UUID") from e


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
