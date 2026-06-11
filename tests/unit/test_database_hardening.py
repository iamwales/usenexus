from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from nexus_core.models.orm import ApiKey, Connection, Document, Organization, QueryLog, SyncJob


def test_alembic_has_single_head() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    config = Config(str(repo_root / "services/api/alembic.ini"))
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == ["0002"]


def test_query_log_api_key_fk_sets_null_on_key_delete() -> None:
    foreign_key = next(iter(QueryLog.__table__.c.api_key_id.foreign_keys))

    assert foreign_key.ondelete == "SET NULL"


def test_tenant_status_indexes_are_declared() -> None:
    expected = {
        Connection.__table__: "idx_connection_org_status",
        Document.__table__: "idx_document_org_status",
        ApiKey.__table__: "idx_api_key_org_revoked",
        SyncJob.__table__: "idx_sync_job_org_status",
        QueryLog.__table__: "idx_query_log_org_created",
    }

    for table, index_name in expected.items():
        assert index_name in {index.name for index in table.indexes}


def test_delete_cascade_relationships_are_passive() -> None:
    assert Organization.connections.property.passive_deletes
    assert Organization.api_keys.property.passive_deletes
    assert Organization.query_logs.property.passive_deletes
    assert Connection.credentials.property.passive_deletes
    assert Connection.documents.property.passive_deletes
    assert Connection.sync_jobs.property.passive_deletes


def test_query_logs_store_hash_not_raw_query_text() -> None:
    assert "query_hash" in QueryLog.__table__.columns
    assert "query_text" not in QueryLog.__table__.columns
