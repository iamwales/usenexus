"""
Regression tests for webhook routing helpers.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from nexus_api.routers import webhooks


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.writes: list[tuple[str, str, int]] = []

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int) -> None:
        self.writes.append((key, value, ex))
        self.values[key] = value


class FakeSession:
    def __init__(self, tenant_id: uuid.UUID | None) -> None:
        self.tenant_id = tenant_id

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def scalar(self, statement) -> uuid.UUID | None:
        return self.tenant_id


def make_request(redis: FakeRedis | None = None) -> SimpleNamespace:
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=redis)))


async def test_tenant_lookup_returns_cached_connection_mapping() -> None:
    connection_id = str(uuid.uuid4())
    redis = FakeRedis()
    redis.values[f"connection_org:{connection_id}"] = "tenant_cached"

    tenant_id = await webhooks._get_tenant_id_for_connection(connection_id, make_request(redis))

    assert tenant_id == "tenant_cached"


async def test_tenant_lookup_falls_back_to_db_and_caches(monkeypatch) -> None:
    connection_id = str(uuid.uuid4())
    tenant_uuid = uuid.uuid4()
    redis = FakeRedis()

    monkeypatch.setattr(webhooks, "AsyncSessionLocal", lambda: FakeSession(tenant_uuid))

    tenant_id = await webhooks._get_tenant_id_for_connection(connection_id, make_request(redis))

    assert tenant_id == str(tenant_uuid)
    assert redis.writes == [
        (
            f"connection_org:{connection_id}",
            str(tenant_uuid),
            webhooks._CONNECTION_TENANT_CACHE_TTL_SECONDS,
        )
    ]


def test_producer_running_check_is_defensive() -> None:
    class DoneTask:
        def done(self) -> bool:
            return False

    running_producer = SimpleNamespace(_sender=SimpleNamespace(sender_task=DoneTask()))
    missing_sender_producer = SimpleNamespace()

    assert webhooks._producer_is_running(running_producer)
    assert not webhooks._producer_is_running(missing_sender_producer)
    assert not webhooks._producer_is_running(None)
