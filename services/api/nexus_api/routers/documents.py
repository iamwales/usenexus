from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from nexus_core.database import get_db
from nexus_core.models.orm import Document
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.dependencies import require_scopes
from nexus_api.errors import api_error

router = APIRouter()

DbSession = Annotated[AsyncSession, Depends(get_db)]


class DocumentOut(BaseModel):
    id: str
    connection_id: str
    connector_id: str | None = None
    external_id: str
    resource_type: str
    title: str | None
    source_url: str | None
    chunk_count: int
    status: str
    indexed_at: datetime | None
    modified_at: datetime | None
    error: str | None


@router.get(
    "/documents",
    response_model=list[DocumentOut],
    dependencies=[Depends(require_scopes("query"))],
)
async def list_documents(
    request: Request,
    db: DbSession,
    connector: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[DocumentOut]:
    org_id = uuid.UUID(request.state.org_id)
    from nexus_core.models.orm import Connection

    stmt = (
        select(Document, Connection.connector_id)
        .join(Connection, Document.connection_id == Connection.id)
        .where(Document.org_id == org_id)
    )
    if connector:
        stmt = stmt.where(Connection.connector_id == connector)
    if status:
        stmt = stmt.where(Document.status == status)
    stmt = stmt.order_by(Document.indexed_at.desc().nullslast()).offset(offset).limit(limit)

    rows = (await db.execute(stmt)).all()
    return [
        DocumentOut(
            id=str(document.id),
            connection_id=str(document.connection_id),
            connector_id=connector_id,
            external_id=document.external_id,
            resource_type=document.resource_type,
            title=document.title,
            source_url=document.source_url,
            chunk_count=document.chunk_count,
            status=document.status,
            indexed_at=document.indexed_at,
            modified_at=document.modified_at,
            error=document.error,
        )
        for document, connector_id in rows
    ]


@router.delete(
    "/documents/{document_id}",
    status_code=204,
    dependencies=[Depends(require_scopes("manage"))],
)
async def delete_document(
    document_id: str,
    request: Request,
    db: DbSession,
) -> None:
    org_id = uuid.UUID(request.state.org_id)
    document_uuid = _parse_document_id(document_id)
    doc = await db.scalar(
        select(Document).where(
            Document.id == document_uuid,
            Document.org_id == org_id,
        )
    )
    if not doc:
        raise api_error(404, "document_not_found", "Document not found")

    await db.execute(update(Document).where(Document.id == doc.id).values(status="deleted"))


def _parse_document_id(document_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(document_id)
    except ValueError as e:
        raise api_error(400, "invalid_document_id", "Document id must be a valid UUID") from e
