"""
Unit tests for Google Drive connector.
Tests webhook parsing, ACL extraction, and content type filtering.
No real HTTP calls — all mocked via httpx.MockTransport.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from nexus_connectors.google_drive.connector import GoogleDriveConnector
from nexus_core.schemas.domain import ChangeEventType, OAuthCredentials


def make_credentials() -> OAuthCredentials:
    return OAuthCredentials(
        connection_id=uuid.uuid4(),
        access_token="test_token",
        refresh_token="test_refresh",
    )


class TestGoogleDriveWebhookParsing:
    def setup_method(self):
        self.connector = GoogleDriveConnector()

    @pytest.mark.asyncio
    async def test_sync_event_returns_empty(self):
        """Initial sync handshake should not produce events."""
        events = await self.connector.parse_webhook(
            payload={},
            headers={
                "x-goog-resource-state": "sync",
                "x-goog-channel-token": "test_secret",
            },
        )
        assert events == []

    @pytest.mark.asyncio
    async def test_invalid_token_returns_empty(self):
        events = await self.connector.parse_webhook(
            payload={"fileIds": ["file_123"]},
            headers={
                "x-goog-resource-state": "update",
                "x-goog-channel-token": "WRONG_TOKEN",
            },
        )
        assert events == []

    @pytest.mark.asyncio
    async def test_update_event_produces_change_events(self):
        with patch("nexus_connectors.google_drive.connector.settings") as mock_settings:
            mock_settings.webhook_signing_secret = "correct_secret"
            events = await self.connector.parse_webhook(
                payload={
                    "fileIds": ["file_abc", "file_xyz"],
                    "tenantId": "org_123",
                    "connectionId": "conn_456",
                },
                headers={
                    "x-goog-resource-state": "update",
                    "x-goog-channel-token": "correct_secret",
                },
            )
        assert len(events) == 2
        assert all(e.event_type == ChangeEventType.UPDATED for e in events)
        assert {e.resource_id for e in events} == {"file_abc", "file_xyz"}

    @pytest.mark.asyncio
    async def test_trash_event_produces_deleted_events(self):
        with patch("nexus_connectors.google_drive.connector.settings") as mock_settings:
            mock_settings.webhook_signing_secret = "correct_secret"
            events = await self.connector.parse_webhook(
                payload={"fileIds": ["file_gone"], "tenantId": "t1", "connectionId": "c1"},
                headers={
                    "x-goog-resource-state": "trash",
                    "x-goog-channel-token": "correct_secret",
                },
            )
        assert len(events) == 1
        assert events[0].event_type == ChangeEventType.DELETED


class TestGoogleDriveACLExtraction:
    def setup_method(self):
        self.connector = GoogleDriveConnector()

    def test_user_permission_extracted(self):
        permissions = [
            {"type": "user", "emailAddress": "alice@company.com", "role": "writer"},
            {"type": "user", "emailAddress": "bob@company.com", "role": "reader"},
        ]
        acl = self.connector._extract_acl(permissions)
        assert "alice@company.com" in acl
        assert "bob@company.com" in acl

    def test_public_permission_returns_public(self):
        permissions = [
            {"type": "anyone", "role": "reader"},
            {"type": "user", "emailAddress": "alice@company.com", "role": "owner"},
        ]
        acl = self.connector._extract_acl(permissions)
        assert acl == ["public"]

    def test_group_permission_extracted(self):
        permissions = [
            {"type": "group", "emailAddress": "team-engineering@company.com", "role": "writer"},
        ]
        acl = self.connector._extract_acl(permissions)
        assert "team-engineering@company.com" in acl

    def test_empty_permissions_returns_empty(self):
        assert self.connector._extract_acl([]) == []


class TestGoogleDriveDateParsing:
    def setup_method(self):
        self.connector = GoogleDriveConnector()

    def test_parses_google_datetime_format(self):
        dt = self.connector._parse_dt("2025-05-15T14:22:00.000Z")
        assert dt is not None
        assert dt.year == 2025
        assert dt.month == 5
        assert dt.day == 15

    def test_returns_none_for_none(self):
        assert self.connector._parse_dt(None) is None

    def test_returns_none_for_invalid(self):
        assert self.connector._parse_dt("not-a-date") is None


class TestGoogleDriveSubscriptions:
    def setup_method(self):
        self.connector = GoogleDriveConnector()

    @pytest.mark.asyncio
    async def test_subscribe_stores_channel_and_resource_id(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/changes/startPageToken"):
                return httpx.Response(200, json={"startPageToken": "page_token_1"})
            if request.url.path.endswith("/changes/watch"):
                body = json.loads(request.content)
                return httpx.Response(
                    200,
                    json={
                        "id": body["id"],
                        "resourceId": "drive_resource_123",
                        "expiration": "1767225600000",
                    },
                )
            return httpx.Response(404)

        self.connector._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

        subscription = await self.connector.subscribe(
            make_credentials(),
            "https://api.example.test/v1/webhooks/google_drive/conn_1",
        )

        payload = json.loads(subscription.subscription_id)
        assert payload["resource_id"] == "drive_resource_123"
        assert uuid.UUID(payload["channel_id"])

    @pytest.mark.asyncio
    async def test_unsubscribe_uses_channel_and_resource_id(self):
        requests: list[dict] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(json.loads(request.content))
            return httpx.Response(200)

        self.connector._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        subscription_id = self.connector._encode_subscription_id(
            "channel_123",
            "resource_456",
        )

        await self.connector.unsubscribe(make_credentials(), subscription_id)

        assert requests == [{"id": "channel_123", "resourceId": "resource_456"}]


class TestGoogleDriveContentTypeFiltering:
    """Ensure unsupported MIME types are skipped."""

    def setup_method(self):
        self.connector = GoogleDriveConnector()

    @pytest.mark.asyncio
    async def test_unsupported_mime_returns_none(self):
        """Binary files like .exe should be skipped."""
        file_meta = {
            "id": "file_123",
            "mimeType": "application/octet-stream",
            "name": "binary.exe",
            "permissions": [],
            "owners": [],
        }
        creds = make_credentials()
        result = await self.connector._file_meta_to_resource(file_meta, creds)
        assert result is None

    @pytest.mark.asyncio
    async def test_google_doc_triggers_export(self):
        """Google Docs should be exported as plain text."""
        import httpx

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.text = "This is the document content."
        mock_response.headers = {}

        file_meta = {
            "id": "doc_123",
            "mimeType": "application/vnd.google-apps.document",
            "name": "My Doc",
            "modifiedTime": "2025-05-01T10:00:00Z",
            "createdTime": "2025-01-01T10:00:00Z",
            "webViewLink": "https://docs.google.com/doc/123",
            "permissions": [{"type": "user", "emailAddress": "alice@co.com", "role": "owner"}],
            "owners": [{"emailAddress": "alice@co.com"}],
        }
        creds = make_credentials()

        with patch.object(
            self.connector, "_extract_content", new_callable=AsyncMock
        ) as mock_extract:
            mock_extract.return_value = "This is the document content."
            resource = await self.connector._file_meta_to_resource(file_meta, creds)

        assert resource is not None
        assert resource.content == "This is the document content."
        assert resource.title == "My Doc"
        assert resource.author_email == "alice@co.com"
