"""
Query Router — POST /v1/query

Supports both regular JSON responses and Server-Sent Events (SSE) streaming.
"""

from __future__ import annotations

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from nexus_core.config import get_settings
from nexus_core.database import get_db
from nexus_core.logging import get_logger
from nexus_core.models.orm import QueryLog
from nexus_core.schemas.domain import QueryResponse
from nexus_retriever.engine import QueryEngine
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.dependencies import require_scopes

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter()

DbSession = Annotated[AsyncSession, Depends(get_db)]


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    connectors: list[str] | None = Field(
        None,
        description="Filter to specific connectors. None = all connected.",
    )
    top_k: int = Field(default=5, ge=1, le=20)
    stream: bool = False
    user_email: str | None = Field(
        None,
        description="User email for per-user ACL filtering.",
    )

    @field_validator("connectors")
    @classmethod
    def validate_connectors(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        from nexus_connectors.registry import is_supported

        invalid = [c for c in v if not is_supported(c)]
        if invalid:
            raise ValueError(f"Unsupported connectors: {invalid}")
        return v


def get_query_engine(request: Request) -> QueryEngine:
    return QueryEngine(
        qdrant=request.app.state.qdrant,
        es=request.app.state.es,
        redis=request.app.state.redis,
    )


QueryEngineDep = Annotated[QueryEngine, Depends(get_query_engine)]


@router.post(
    "/query",
    response_model=QueryResponse,
    dependencies=[Depends(require_scopes("query"))],
)
async def query(
    body: QueryRequest,
    request: Request,
    db: DbSession,
    engine: QueryEngineDep,
) -> QueryResponse | StreamingResponse:
    org_id: str = request.state.org_id
    user_email: str | None = getattr(request.state, "user_email", None) or body.user_email

    if body.stream:
        return StreamingResponse(
            _stream_response(engine, body, org_id, user_email),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    response = await engine.query(
        query=body.query,
        tenant_id=org_id,
        connector_ids=body.connectors,
        user_email=user_email,
        top_k=body.top_k,
        stream=False,
    )

    # Async fire-and-forget query log
    await _log_query(
        db,
        org_id,
        body.query,
        response,
        getattr(request.state, "api_key_id", None),
    )
    return response


async def _stream_response(
    engine: QueryEngine,
    body: QueryRequest,
    org_id: str,
    user_email: str | None,
):
    """SSE event generator."""
    try:
        async for event in engine.query_stream(
            query=body.query,
            tenant_id=org_id,
            connector_ids=body.connectors,
            user_email=user_email,
            top_k=body.top_k,
        ):
            yield f"data: {json.dumps(event)}\n\n"
    except Exception as e:
        logger.error("query.stream_error", error=str(e))
        yield f"data: {json.dumps({'type': 'error', 'message': 'Query failed'})}\n\n"


async def _log_query(
    db: AsyncSession,
    org_id: str,
    query_text: str,
    response: QueryResponse,
    api_key_id: str | None,
) -> None:
    import hashlib

    try:
        log = QueryLog(
            org_id=uuid.UUID(org_id),
            api_key_id=uuid.UUID(api_key_id) if api_key_id else None,
            query_hash=hashlib.sha256(query_text.encode()).hexdigest(),
            response_tokens=None,
            latency_ms=response.latency_ms,
            source_count=len(response.citations),
            cached=response.cached,
            connectors_used=list({c.connector for c in response.citations}),
        )
        db.add(log)
        await db.commit()
    except Exception as e:
        logger.warning("query.log_failed", error=str(e))
