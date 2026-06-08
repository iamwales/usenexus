"""
AuthMiddleware — validates JWT tokens and API keys.

API keys: Bearer nxs_live_<key>
  - Hash the raw key with SHA-256, look up in api_keys table
  - Attach org_id and key scopes to request state

JWT: Bearer eyJ...
  - Validate signature with JWT_SECRET
  - Attach org_id and user_email to request state

Public routes (no auth required): /health, /v1/webhooks/*
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

import jwt
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from nexus_core.config import get_settings
from nexus_core.database import AsyncSessionLocal
from nexus_core.logging import get_logger
from nexus_core.models.orm import ApiKey
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware

logger = get_logger(__name__)
settings = get_settings()

_PUBLIC_PREFIXES = ("/health", "/v1/webhooks/", "/docs", "/openapi.json")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Skip auth for public routes
        if any(path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"error": "Missing Authorization header"},
            )

        token = auth_header.removeprefix("Bearer ").strip()

        try:
            if token.startswith("nxs_"):
                org_id, scopes, rate_limit_rpm = await self._validate_api_key(token)
                request.state.org_id = str(org_id)
                request.state.user_email = None
                request.state.scopes = scopes
                request.state.rate_limit_rpm = rate_limit_rpm
                request.state.auth_type = "api_key"
            else:
                org_id, user_email = self._validate_jwt(token)
                request.state.org_id = str(org_id)
                request.state.user_email = user_email
                request.state.scopes = ["query", "manage"]
                request.state.auth_type = "jwt"
        except AuthError as e:
            return JSONResponse(status_code=401, content={"error": str(e)})
        except Exception as e:
            logger.error("auth.unexpected_error", error=str(e))
            return JSONResponse(status_code=500, content={"error": "Internal auth error"})

        return await call_next(request)

    async def _validate_api_key(self, raw_key: str) -> tuple[uuid.UUID, list[str], int]:
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        async with AsyncSessionLocal() as session:
            row = await session.scalar(
                select(ApiKey).where(
                    ApiKey.key_hash == key_hash,
                    ApiKey.revoked_at.is_(None),
                )
            )
        if not row:
            raise AuthError("Invalid API key")
        if row.expires_at and row.expires_at < datetime.now(tz=UTC):
            raise AuthError("API key expired")

        # Update last_used_at asynchronously (fire and forget)
        async with AsyncSessionLocal() as session:
            from sqlalchemy import update

            await session.execute(
                update(ApiKey).where(ApiKey.id == row.id).values(last_used_at=datetime.now(tz=UTC))
            )
            await session.commit()

        return row.org_id, list(row.scopes or ["query"]), row.rate_limit_rpm

    def _validate_jwt(self, token: str) -> tuple[uuid.UUID, str | None]:
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=[settings.jwt_algorithm],
            )
        except jwt.ExpiredSignatureError as e:
            raise AuthError("Token expired") from e
        except jwt.InvalidTokenError as e:
            raise AuthError(f"Invalid token: {e}") from e

        org_id_str = payload.get("org_id")
        user_email = payload.get("email")
        if not org_id_str:
            raise AuthError("Token missing org_id claim")

        return uuid.UUID(org_id_str), user_email


class AuthError(Exception):
    pass
