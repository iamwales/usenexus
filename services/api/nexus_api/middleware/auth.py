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
from nexus_core.config import get_settings
from nexus_core.database import AsyncSessionLocal
from nexus_core.logging import get_logger
from nexus_core.models.orm import ApiKey, Organization
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware

from nexus_api.errors import error_response

logger = get_logger(__name__)
settings = get_settings()

_PUBLIC_PREFIXES = ("/health", "/v1/webhooks/", "/docs", "/openapi.json")
_PUBLIC_PATHS = {"/v1/connections/oauth/callback"}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Skip auth for public routes
        if path in _PUBLIC_PATHS or any(path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return error_response(
                401,
                "missing_authorization",
                "Missing Authorization header",
                request_id=request.headers.get("x-request-id"),
            )

        token = auth_header.removeprefix("Bearer ").strip()

        try:
            if token.startswith("nxs_"):
                org_id, scopes, rate_limit_rpm, api_key_id = await self._validate_api_key(token)
                request.state.org_id = str(org_id)
                request.state.user_email = None
                request.state.scopes = scopes
                request.state.rate_limit_rpm = rate_limit_rpm
                request.state.api_key_id = str(api_key_id)
                request.state.auth_type = "api_key"
            else:
                org_id, user_email = self._validate_jwt(token)
                await self._ensure_org_active(org_id)
                request.state.org_id = str(org_id)
                request.state.user_email = user_email
                request.state.scopes = ["query", "manage"]
                request.state.auth_type = "jwt"
        except AuthError as e:
            return error_response(
                401,
                e.code,
                str(e),
                request_id=request.headers.get("x-request-id"),
            )
        except Exception as e:
            logger.error("auth.unexpected_error", error=str(e))
            return error_response(
                500,
                "internal_auth_error",
                "Internal auth error",
                request_id=request.headers.get("x-request-id"),
            )

        return await call_next(request)

    async def _validate_api_key(self, raw_key: str) -> tuple[uuid.UUID, list[str], int, uuid.UUID]:
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        async with AsyncSessionLocal() as session:
            row = await session.scalar(
                select(ApiKey)
                .join(Organization, ApiKey.org_id == Organization.id)
                .where(
                    ApiKey.key_hash == key_hash,
                    ApiKey.revoked_at.is_(None),
                    Organization.deleted_at.is_(None),
                )
            )
            if not row:
                raise AuthError("Invalid API key", code="invalid_api_key")
            if row.expires_at and row.expires_at < datetime.now(tz=UTC):
                raise AuthError("API key expired", code="api_key_expired")

            from sqlalchemy import update

            await session.execute(
                update(ApiKey).where(ApiKey.id == row.id).values(last_used_at=datetime.now(tz=UTC))
            )
            await session.commit()

            return row.org_id, list(row.scopes or ["query"]), row.rate_limit_rpm, row.id

    async def _ensure_org_active(self, org_id: uuid.UUID) -> None:
        async with AsyncSessionLocal() as session:
            exists = await session.scalar(
                select(Organization.id).where(
                    Organization.id == org_id,
                    Organization.deleted_at.is_(None),
                )
            )
        if not exists:
            raise AuthError("Organization not found", code="organization_not_found")

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
            raise AuthError("Token missing org_id claim", code="token_missing_org")

        return uuid.UUID(org_id_str), user_email


class AuthError(Exception):
    def __init__(self, message: str, *, code: str = "unauthorized") -> None:
        self.code = code
        super().__init__(message)
