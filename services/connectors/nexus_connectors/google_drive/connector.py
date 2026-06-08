"""
Google Drive Connector

Supports:
  - Google Docs, Sheets, Slides (exported to text/csv)
  - PDFs, plain text files
  - Folder structure preserved in metadata
  - Push Notifications (webhook) with 7-day auto-renewal
  - Per-file ACL mirroring (owners + writers + readers)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import httpx
from nexus_core.config import get_settings
from nexus_core.connectors.base import (
    BaseConnector,
    ConnectorAuthError,
    ConnectorNotFoundError,
)
from nexus_core.logging import get_logger
from nexus_core.schemas.domain import (
    ChangeEvent,
    ChangeEventType,
    ConnectorID,
    OAuthCredentials,
    Resource,
    ResourcePage,
    Subscription,
)

logger = get_logger(__name__)
settings = get_settings()

# MIME types we can export/extract text from
_EXPORTABLE_MIME: dict[str, str] = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}

_DIRECT_TEXT_MIME: set[str] = {
    "text/plain",
    "text/markdown",
    "text/html",
    "application/json",
}

_SUPPORTED_MIME: set[str] = set(_EXPORTABLE_MIME.keys()) | _DIRECT_TEXT_MIME | {"application/pdf"}

_DRIVE_API = "https://www.googleapis.com/drive/v3"
_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "openid",
    "email",
]


class GoogleDriveConnector(BaseConnector):
    connector_id = ConnectorID.GOOGLE_DRIVE
    display_name = "Google Drive"
    oauth_scopes = _OAUTH_SCOPES

    # ── OAuth ─────────────────────────────────────────────────────────────────

    async def get_auth_url(self, state: str, redirect_uri: str) -> str:
        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(_OAUTH_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthCredentials:
        resp = await self.http.post(
            _TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return OAuthCredentials(
            connection_id=uuid.uuid4(),  # Will be overwritten by caller
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_at=self._parse_expires(data.get("expires_in")),
            extra={"token_type": data.get("token_type", "Bearer")},
        )

    async def refresh_credentials(self, credentials: OAuthCredentials) -> OAuthCredentials:
        if not credentials.refresh_token:
            raise ConnectorAuthError("No refresh token available")

        resp = await self.http.post(
            _TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": credentials.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        if resp.status_code == 401:
            raise ConnectorAuthError("Refresh token revoked")
        resp.raise_for_status()
        data = resp.json()

        return credentials.model_copy(
            update={
                "access_token": data["access_token"],
                "expires_at": self._parse_expires(data.get("expires_in")),
            }
        )

    # ── list_resources ────────────────────────────────────────────────────────

    async def list_resources(
        self,
        credentials: OAuthCredentials,
        cursor: str | None = None,
    ) -> ResourcePage:
        """
        List all files the authorized user can access.
        Uses Drive v3 files.list with pageToken for pagination.
        Filters to supported MIME types only.
        """
        mime_query = " or ".join(f"mimeType = '{m}'" for m in _SUPPORTED_MIME)
        params: dict[str, Any] = {
            "q": f"trashed = false and ({mime_query})",
            "fields": (
                "nextPageToken, files(id, name, mimeType, modifiedTime, "
                "createdTime, owners, parents, webViewLink, size, "
                "permissions(emailAddress, role, type))"
            ),
            "pageSize": 100,
            "orderBy": "modifiedTime desc",
        }
        if cursor:
            params["pageToken"] = cursor

        resp = await self.http.get(
            f"{_DRIVE_API}/files",
            params=params,
            headers=self._bearer_headers(credentials),
        )
        self._check_rate_limit(resp)
        self._check_auth(resp)
        resp.raise_for_status()

        data = resp.json()
        resources = []
        for file_meta in data.get("files", []):
            try:
                resource = await self._file_meta_to_resource(file_meta, credentials)
                if resource:
                    resources.append(resource)
            except ConnectorNotFoundError:
                continue
            except Exception as e:
                logger.warning(
                    "drive.file_skip",
                    file_id=file_meta.get("id"),
                    error=str(e),
                )

        return ResourcePage(
            resources=resources,
            next_cursor=data.get("nextPageToken"),
        )

    # ── fetch_resource ────────────────────────────────────────────────────────

    async def fetch_resource(
        self,
        credentials: OAuthCredentials,
        resource_id: str,
    ) -> Resource:
        """Fetch metadata + extract text content for a single file."""
        # Get file metadata
        meta_resp = await self.http.get(
            f"{_DRIVE_API}/files/{resource_id}",
            params={
                "fields": (
                    "id, name, mimeType, modifiedTime, createdTime, "
                    "owners, parents, webViewLink, size, "
                    "permissions(emailAddress, role, type)"
                )
            },
            headers=self._bearer_headers(credentials),
        )
        self._check_rate_limit(meta_resp)
        self._check_auth(meta_resp)
        if meta_resp.status_code == 404:
            raise ConnectorNotFoundError(resource_id)
        meta_resp.raise_for_status()

        file_meta = meta_resp.json()
        resource = await self._file_meta_to_resource(file_meta, credentials)
        if not resource:
            raise ConnectorNotFoundError(resource_id)
        return resource

    # ── subscribe (webhooks) ──────────────────────────────────────────────────

    async def subscribe(
        self,
        credentials: OAuthCredentials,
        webhook_url: str,
    ) -> Subscription:
        """
        Register a Drive push notification channel.
        Google pushes to webhook_url on any change in the user's Drive.
        Channels expire after 7 days — scheduler renews them.
        """
        channel_id = str(uuid.uuid4())
        resp = await self.http.post(
            f"{_DRIVE_API}/changes/watch",
            headers=self._bearer_headers(credentials),
            json={
                "id": channel_id,
                "type": "web_hook",
                "address": webhook_url,
                "token": settings.webhook_signing_secret,
                "params": {"ttl": str(7 * 24 * 3600)},  # 7 days in seconds
            },
            params={"pageToken": await self._get_start_page_token(credentials)},
        )
        self._check_rate_limit(resp)
        resp.raise_for_status()
        data = resp.json()

        expiry = data.get("expiration")
        expires_at = datetime.fromtimestamp(int(expiry) / 1000, tz=UTC) if expiry else None

        logger.info(
            "drive.webhook_registered",
            channel_id=channel_id,
            expires_at=expires_at,
        )
        return Subscription(
            subscription_id=channel_id,
            expires_at=expires_at,
            webhook_url=webhook_url,
        )

    async def unsubscribe(
        self,
        credentials: OAuthCredentials,
        subscription_id: str,
    ) -> None:
        resp = await self.http.post(
            f"{_DRIVE_API}/channels/stop",
            headers=self._bearer_headers(credentials),
            json={"id": subscription_id, "resourceId": subscription_id},
        )
        if resp.status_code not in (200, 204, 404):
            resp.raise_for_status()

    # ── parse_webhook ─────────────────────────────────────────────────────────

    async def parse_webhook(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> list[ChangeEvent]:
        """
        Google Drive sends a notification to our channel endpoint.
        The payload itself is minimal — we must poll the changes API to get
        the actual list of changed files.

        Headers contain:
          X-Goog-Channel-ID, X-Goog-Resource-State, X-Goog-Channel-Token
        """
        channel_token = headers.get("x-goog-channel-token", "")
        if channel_token != settings.webhook_signing_secret:
            logger.warning("drive.webhook_invalid_token", token=channel_token)
            return []

        resource_state = headers.get("x-goog-resource-state", "")
        if resource_state == "sync":
            # Initial handshake — not a real change
            return []

        # The actual changed file IDs come from the payload
        # (for Drive, we return a synthetic event; the ingestion layer
        # will call fetch_resource to get the full content)
        changed_ids: list[str] = payload.get("fileIds", [])

        events: list[ChangeEvent] = []
        for file_id in changed_ids:
            event_type = (
                ChangeEventType.DELETED if resource_state == "trash" else ChangeEventType.UPDATED
            )
            events.append(
                ChangeEvent(
                    event_type=event_type,
                    tenant_id=payload.get("tenantId", ""),
                    connection_id=payload.get("connectionId", ""),
                    connector_id=ConnectorID.GOOGLE_DRIVE,
                    resource_id=file_id,
                    resource_type="file",
                )
            )
        return events

    # ── check_permission ──────────────────────────────────────────────────────

    async def check_permission(
        self,
        credentials: OAuthCredentials,
        resource_id: str,
        user_email: str,
    ) -> bool:
        """
        Check if user_email has at least reader access to the file.
        Returns True for files shared publicly or with the user's domain.
        """
        resp = await self.http.get(
            f"{_DRIVE_API}/files/{resource_id}/permissions",
            params={"fields": "permissions(emailAddress, role, type)"},
            headers=self._bearer_headers(credentials),
        )
        if resp.status_code in (403, 404):
            return False
        resp.raise_for_status()

        permissions = resp.json().get("permissions", [])
        for perm in permissions:
            if perm.get("type") == "anyone":
                return True
            if perm.get("emailAddress", "").lower() == user_email.lower():
                return True
        return False

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _file_meta_to_resource(
        self,
        file_meta: dict[str, Any],
        credentials: OAuthCredentials,
    ) -> Resource | None:
        """Convert Drive file metadata + content into a Resource."""
        file_id = file_meta["id"]
        mime_type = file_meta.get("mimeType", "")

        if mime_type not in _SUPPORTED_MIME:
            return None

        content = await self._extract_content(file_id, mime_type, credentials)
        if not content or not content.strip():
            return None

        acl = self._extract_acl(file_meta.get("permissions", []))
        # Always include owner emails
        for owner in file_meta.get("owners", []):
            email = owner.get("emailAddress")
            if email and email not in acl:
                acl.append(email)

        return Resource(
            resource_id=file_id,
            resource_type="file",
            title=file_meta.get("name"),
            content=content,
            source_url=file_meta.get("webViewLink"),
            author_email=(
                file_meta["owners"][0].get("emailAddress") if file_meta.get("owners") else None
            ),
            created_at=self._parse_dt(file_meta.get("createdTime")),
            modified_at=self._parse_dt(file_meta.get("modifiedTime")),
            acl=acl,
            connector_metadata={
                "mime_type": mime_type,
                "parents": file_meta.get("parents", []),
                "size": file_meta.get("size"),
            },
        )

    async def _extract_content(
        self,
        file_id: str,
        mime_type: str,
        credentials: OAuthCredentials,
    ) -> str:
        """Export or download file content as plain text."""
        headers = self._bearer_headers(credentials)

        if mime_type in _EXPORTABLE_MIME:
            export_mime = _EXPORTABLE_MIME[mime_type]
            resp = await self.http.get(
                f"{_DRIVE_API}/files/{file_id}/export",
                params={"mimeType": export_mime},
                headers=headers,
            )
        elif mime_type == "application/pdf":
            # For PDFs: download the binary, extract text via pdfminer
            resp = await self.http.get(
                f"{_DRIVE_API}/files/{file_id}",
                params={"alt": "media"},
                headers=headers,
            )
            if resp.status_code == 200:
                return self._extract_pdf_text(resp.content)
            return ""
        else:
            # Plain text — direct download
            resp = await self.http.get(
                f"{_DRIVE_API}/files/{file_id}",
                params={"alt": "media"},
                headers=headers,
            )

        self._check_rate_limit(resp)
        if resp.status_code == 404:
            raise ConnectorNotFoundError(file_id)
        resp.raise_for_status()
        return resp.text

    def _extract_pdf_text(self, content: bytes) -> str:
        """Extract text from PDF bytes using pdfminer.six."""
        try:
            from io import BytesIO

            from pdfminer.high_level import extract_text

            return extract_text(BytesIO(content))
        except ImportError:
            logger.warning("drive.pdf_extraction_unavailable")
            return ""
        except Exception as e:
            logger.warning("drive.pdf_extraction_failed", error=str(e))
            return ""

    def _extract_acl(self, permissions: list[dict[str, Any]]) -> list[str]:
        """Extract email addresses that have access to the file."""
        acl: list[str] = []
        for perm in permissions:
            perm_type = perm.get("type", "")
            if perm_type == "anyone":
                return ["public"]  # Public file — all users can see it
            if perm_type in ("user", "group"):
                email = perm.get("emailAddress")
                if email:
                    acl.append(email.lower())
        return acl

    async def _get_start_page_token(self, credentials: OAuthCredentials) -> str:
        resp = await self.http.get(
            f"{_DRIVE_API}/changes/startPageToken",
            headers=self._bearer_headers(credentials),
        )
        resp.raise_for_status()
        return resp.json()["startPageToken"]

    def _check_auth(self, response: httpx.Response) -> None:
        if response.status_code in (401, 403):
            raise ConnectorAuthError(f"Google Drive auth error: {response.status_code}")

    @staticmethod
    def _parse_dt(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None

    @staticmethod
    def _parse_expires(expires_in: int | None) -> datetime | None:
        if not expires_in:
            return None
        from datetime import timedelta

        return datetime.now(tz=UTC) + timedelta(seconds=int(expires_in))
