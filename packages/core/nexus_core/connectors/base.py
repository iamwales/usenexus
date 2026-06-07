"""
BaseConnector — the MCP adapter contract.

Every connector must subclass this and implement all abstract methods.
The connector framework handles retry, rate limiting, and error recording.
Connectors focus purely on source-specific logic.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any

import httpx

from nexus_core.logging import get_logger
from nexus_core.schemas.domain import (
    ChangeEvent,
    OAuthCredentials,
    Resource,
    ResourcePage,
    Subscription,
)

logger = get_logger(__name__)


class RateLimitError(Exception):
    def __init__(self, retry_after: float = 60.0) -> None:
        self.retry_after = retry_after
        super().__init__(f"Rate limited; retry after {retry_after}s")


class ConnectorAuthError(Exception):
    """OAuth token invalid or revoked — triggers connection status → error."""


class ConnectorNotFoundError(Exception):
    """Resource no longer exists in the source system."""


class BaseConnector(ABC):
    """
    Abstract base for all Nexus connectors.

    Lifecycle:
        1. list_resources()    — paginated full resource discovery
        2. fetch_resource()    — fetch one resource's full content
        3. subscribe()         — register webhook for live updates
        4. parse_webhook()     — normalize incoming webhook to ChangeEvents
        5. check_permission()  — ACL check at query time
        6. refresh_credentials() — refresh expired OAuth tokens (default impl)
    """

    # Subclasses MUST define these
    connector_id: str
    display_name: str
    oauth_scopes: list[str]

    # Override to configure retry behavior
    max_retries: int = 3
    base_wait_seconds: float = 1.0
    max_wait_seconds: float = 60.0

    def __init__(self) -> None:
        self._http: httpx.AsyncClient | None = None

    @property
    def http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=True,
                headers={"User-Agent": "Nexus/1.0 (+https://usenexus.ai)"},
            )
        return self._http

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()

    # ── Abstract interface ────────────────────────────────────────────────────

    @abstractmethod
    async def list_resources(
        self,
        credentials: OAuthCredentials,
        cursor: str | None = None,
    ) -> ResourcePage:
        """
        Return a page of all indexable resources.
        Must be paginated — never load everything into memory.
        cursor=None means first page.
        """

    @abstractmethod
    async def fetch_resource(
        self,
        credentials: OAuthCredentials,
        resource_id: str,
    ) -> Resource:
        """
        Fetch the full content and metadata for a single resource.
        Raise ConnectorNotFoundError if the resource no longer exists.
        """

    @abstractmethod
    async def subscribe(
        self,
        credentials: OAuthCredentials,
        webhook_url: str,
    ) -> Subscription:
        """
        Register a webhook so the source system pushes change events to Nexus.
        Returns a Subscription with the subscription ID and optional expiry.
        """

    @abstractmethod
    async def parse_webhook(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> list[ChangeEvent]:
        """
        Parse a raw webhook payload into a list of normalized ChangeEvents.
        One webhook may contain multiple changed resources.
        Should validate the HMAC signature in headers.
        Return [] if the event is irrelevant (e.g. a heartbeat ping).
        """

    @abstractmethod
    async def check_permission(
        self,
        credentials: OAuthCredentials,
        resource_id: str,
        user_email: str,
    ) -> bool:
        """
        Return True if user_email is allowed to access resource_id
        according to the source system's ACL.
        Called at query time for per-user permission filtering.
        """

    # ── Default implementations ───────────────────────────────────────────────

    async def refresh_credentials(
        self,
        credentials: OAuthCredentials,
    ) -> OAuthCredentials:
        """
        Refresh an expired access token using the refresh token.
        Override per-connector if the OAuth endpoint differs from standard.
        Default raises NotImplementedError — connectors with short-lived tokens
        must override.
        """
        raise NotImplementedError(
            f"Connector {self.connector_id} must implement refresh_credentials"
        )

    async def unsubscribe(
        self,
        credentials: OAuthCredentials,
        subscription_id: str,
    ) -> None:
        """
        Cancel a webhook subscription. Called when a connection is deleted.
        Default is a no-op — override if the provider requires explicit cleanup.
        """
        return None

    async def get_auth_url(
        self,
        state: str,
        redirect_uri: str,
    ) -> str:
        """Build the OAuth authorization URL."""
        raise NotImplementedError

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> OAuthCredentials:
        """Exchange an OAuth authorization code for tokens."""
        raise NotImplementedError

    # ── Resilient wrappers ────────────────────────────────────────────────────

    async def list_resources_with_retry(
        self,
        credentials: OAuthCredentials,
        cursor: str | None = None,
    ) -> ResourcePage:
        return await self._with_retry(self.list_resources, credentials, cursor)

    async def fetch_resource_with_retry(
        self,
        credentials: OAuthCredentials,
        resource_id: str,
    ) -> Resource:
        return await self._with_retry(self.fetch_resource, credentials, resource_id)

    async def _with_retry(self, fn, *args, **kwargs):  # type: ignore[no-untyped-def]
        """
        Execute fn with exponential backoff retry.
        ConnectorAuthError and ConnectorNotFoundError are NOT retried.
        """
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                return await fn(*args, **kwargs)
            except (ConnectorAuthError, ConnectorNotFoundError):
                raise
            except RateLimitError as e:
                wait = min(e.retry_after, self.max_wait_seconds)
                logger.warning(
                    "connector.rate_limited",
                    connector=self.connector_id,
                    retry_after=wait,
                    attempt=attempt,
                )
                await asyncio.sleep(wait)
                last_exc = e
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (401, 403):
                    raise ConnectorAuthError(str(e)) from e
                if e.response.status_code == 404:
                    raise ConnectorNotFoundError(str(e)) from e
                wait_time = self.base_wait_seconds * (2**attempt)
                logger.warning(
                    "connector.http_error",
                    connector=self.connector_id,
                    status=e.response.status_code,
                    attempt=attempt,
                    wait=wait_time,
                )
                await asyncio.sleep(wait_time)
                last_exc = e
            except Exception as e:
                wait_time = self.base_wait_seconds * (2**attempt)
                logger.warning(
                    "connector.error",
                    connector=self.connector_id,
                    error=str(e),
                    attempt=attempt,
                )
                await asyncio.sleep(wait_time)
                last_exc = e

        raise RuntimeError(
            f"Connector {self.connector_id} failed after {self.max_retries} attempts"
        ) from last_exc

    # ── Helpers for subclasses ────────────────────────────────────────────────

    def _bearer_headers(self, credentials: OAuthCredentials) -> dict[str, str]:
        return {"Authorization": f"Bearer {credentials.access_token}"}

    def _check_rate_limit(self, response: httpx.Response) -> None:
        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", 60))
            raise RateLimitError(retry_after=retry_after)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} connector_id={self.connector_id!r}>"
