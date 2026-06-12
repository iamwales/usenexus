from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from nexus_api.dependencies import require_scopes
from nexus_api.errors import api_error, error_payload
from nexus_api.middleware.auth import _PUBLIC_PATHS
from nexus_api.routers.keys import ApiKeyCreate, ApiKeyUpdate
from pydantic import ValidationError


def make_request(scopes: list[str]):
    return SimpleNamespace(state=SimpleNamespace(scopes=scopes))


def test_error_payload_uses_single_api_shape() -> None:
    payload = error_payload(
        "invalid_api_key_id",
        "API key id must be a valid UUID",
        details={"field": "key_id"},
        request_id="req_123",
    )

    assert payload == {
        "error": {
            "code": "invalid_api_key_id",
            "message": "API key id must be a valid UUID",
            "details": {"field": "key_id"},
        },
        "request_id": "req_123",
    }


def test_api_error_sets_structured_detail() -> None:
    exc = api_error(404, "api_key_not_found", "API key not found")

    assert isinstance(exc, HTTPException)
    assert exc.status_code == 404
    assert exc.detail == {
        "code": "api_key_not_found",
        "message": "API key not found",
    }


@pytest.mark.asyncio
async def test_require_scopes_allows_required_scope() -> None:
    dependency = require_scopes("query")

    await dependency(make_request(["query"]))


@pytest.mark.asyncio
async def test_require_scopes_treats_manage_as_admin_scope() -> None:
    dependency = require_scopes("query")

    await dependency(make_request(["manage"]))


@pytest.mark.asyncio
async def test_require_scopes_rejects_missing_scope() -> None:
    dependency = require_scopes("manage")

    with pytest.raises(HTTPException) as exc_info:
        await dependency(make_request(["query"]))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "insufficient_scope"
    assert exc_info.value.detail["details"] == {
        "required": ["manage"],
        "granted": ["query"],
    }


def test_api_key_create_normalizes_allowed_scopes() -> None:
    body = ApiKeyCreate(name="Automation", scopes=["query", "manage", "query"])

    assert body.scopes == ["manage", "query"]


def test_api_key_update_rejects_unknown_scopes() -> None:
    with pytest.raises(ValidationError):
        ApiKeyUpdate(scopes=["query", "admin"])


def test_oauth_callback_is_public_for_provider_redirects() -> None:
    assert "/v1/connections/oauth/callback" in _PUBLIC_PATHS
