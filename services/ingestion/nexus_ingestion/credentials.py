"""
CredentialService — fetches, decrypts, and auto-refreshes OAuth credentials.

Credentials are cached in Redis (encrypted) to avoid per-message DB hits.
Cache TTL is always set to token expiry - 5 minutes.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import redis.asyncio as aioredis
from nexus_core.config import get_settings
from nexus_core.crypto import decrypt_token, encrypt_token
from nexus_core.database import get_db_session
from nexus_core.logging import get_logger
from nexus_core.models.orm import Connection
from nexus_core.models.orm import OAuthCredentials as OAuthCredentialsORM
from nexus_core.schemas.domain import OAuthCredentials
from sqlalchemy import select

logger = get_logger(__name__)
settings = get_settings()

_CACHE_PREFIX = "creds:"
_CACHE_DEFAULT_TTL = 3300  # 55 minutes


class CredentialService:
    def __init__(self, redis_client: aioredis.Redis | None = None) -> None:
        self._redis = redis_client

    async def get(self, connection_id: str) -> OAuthCredentials:
        """
        Fetch credentials for a connection, auto-refreshing if expired.
        """
        # Try cache first
        cached = await self._get_cached(connection_id)
        if cached:
            return cached

        # Load from DB
        creds = await self._load_from_db(connection_id)

        # Refresh if expired (or expiring within 5 minutes)
        if self._is_expiring(creds):
            creds = await self._refresh(connection_id, creds)

        # Cache the result
        await self._cache(connection_id, creds)
        return creds

    async def save(
        self,
        connection_id: uuid.UUID,
        creds: OAuthCredentials,
        kms_key_id: str,
    ) -> None:
        """Encrypt and persist credentials to Postgres."""
        access_enc = encrypt_token(creds.access_token, kms_key_id)
        refresh_enc = (
            encrypt_token(creds.refresh_token, kms_key_id) if creds.refresh_token else None
        )

        async with get_db_session() as session:
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            stmt = (
                pg_insert(OAuthCredentialsORM)
                .values(
                    connection_id=connection_id,
                    access_token_enc=access_enc,
                    refresh_token_enc=refresh_enc,
                    expires_at=creds.expires_at,
                    kms_key_id=kms_key_id,
                    token_metadata=creds.extra,
                )
                .on_conflict_do_update(
                    index_elements=["connection_id"],
                    set_={
                        "access_token_enc": access_enc,
                        "expires_at": creds.expires_at,
                        "token_metadata": creds.extra,
                    },
                )
            )
            await session.execute(stmt)

        # Invalidate cache
        if self._redis:
            await self._redis.delete(f"{_CACHE_PREFIX}{connection_id}")

    async def revoke(self, connection_id: str) -> None:
        async with get_db_session() as session:
            await session.execute(
                OAuthCredentialsORM.__table__.delete().where(
                    OAuthCredentialsORM.connection_id == uuid.UUID(connection_id)
                )
            )
        if self._redis:
            await self._redis.delete(f"{_CACHE_PREFIX}{connection_id}")

    # ── Private ───────────────────────────────────────────────────────────────

    async def _load_from_db(self, connection_id: str) -> OAuthCredentials:
        async with get_db_session() as session:
            row = await session.scalar(
                select(OAuthCredentialsORM).where(
                    OAuthCredentialsORM.connection_id == uuid.UUID(connection_id)
                )
            )
        if not row:
            raise ValueError(f"No credentials found for connection {connection_id}")

        access_token = decrypt_token(row.access_token_enc, row.kms_key_id)
        refresh_token = (
            decrypt_token(row.refresh_token_enc, row.kms_key_id) if row.refresh_token_enc else None
        )
        return OAuthCredentials(
            connection_id=uuid.UUID(connection_id),
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=row.expires_at,
            extra=row.token_metadata or {},
        )

    async def _refresh(self, connection_id: str, creds: OAuthCredentials) -> OAuthCredentials:
        # Load connector_id from DB
        async with get_db_session() as session:
            conn = await session.scalar(
                select(Connection).where(Connection.id == uuid.UUID(connection_id))
            )
        if not conn:
            raise ValueError(f"Connection {connection_id} not found")

        from nexus_connectors.registry import get_connector

        connector = get_connector(conn.connector_id)

        try:
            refreshed = await connector.refresh_credentials(creds)
            await self.save(uuid.UUID(connection_id), refreshed, settings.encryption_key_id)
            logger.info(
                "credentials.refreshed",
                connection_id=connection_id,
                connector_id=conn.connector_id,
            )
            return refreshed
        except Exception as e:
            logger.error(
                "credentials.refresh_failed",
                connection_id=connection_id,
                error=str(e),
            )
            # Mark connection as error state
            async with get_db_session() as session:
                from sqlalchemy import update

                await session.execute(
                    update(Connection)
                    .where(Connection.id == uuid.UUID(connection_id))
                    .values(status="error", error_message=f"Token refresh failed: {e}")
                )
            raise

    async def _get_cached(self, connection_id: str) -> OAuthCredentials | None:
        if not self._redis:
            return None
        raw = await self._redis.get(f"{_CACHE_PREFIX}{connection_id}")
        if not raw:
            return None
        data = json.loads(raw)
        return OAuthCredentials.model_validate(data)

    async def _cache(self, connection_id: str, creds: OAuthCredentials) -> None:
        if not self._redis:
            return
        ttl = _CACHE_DEFAULT_TTL
        if creds.expires_at:
            remaining = (
                int((creds.expires_at - datetime.now(tz=UTC)).total_seconds()) - 300
            )  # 5 min buffer
            ttl = max(60, min(remaining, _CACHE_DEFAULT_TTL))

        await self._redis.set(
            f"{_CACHE_PREFIX}{connection_id}",
            creds.model_dump_json(),
            ex=ttl,
        )

    @staticmethod
    def _is_expiring(creds: OAuthCredentials) -> bool:
        if not creds.expires_at:
            return False
        return creds.expires_at < datetime.now(tz=UTC) + timedelta(minutes=5)
