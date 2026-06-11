"""Database hardening indexes and cascade behavior

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-09 00:00:00
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_connection_org_status",
        "connections",
        ["org_id", "status"],
        unique=False,
    )
    op.create_index(
        "idx_document_org_status",
        "documents",
        ["org_id", "status"],
        unique=False,
    )
    op.create_index(
        "idx_api_key_org_revoked",
        "api_keys",
        ["org_id", "revoked_at"],
        unique=False,
    )
    op.create_index(
        "idx_sync_job_org_status",
        "sync_jobs",
        ["org_id", "status"],
        unique=False,
    )
    op.create_index(
        "idx_query_log_org_created",
        "query_logs",
        ["org_id", "created_at"],
        unique=False,
    )

    op.drop_constraint("query_logs_api_key_id_fkey", "query_logs", type_="foreignkey")
    op.create_foreign_key(
        "query_logs_api_key_id_fkey",
        "query_logs",
        "api_keys",
        ["api_key_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("query_logs_api_key_id_fkey", "query_logs", type_="foreignkey")
    op.create_foreign_key(
        "query_logs_api_key_id_fkey",
        "query_logs",
        "api_keys",
        ["api_key_id"],
        ["id"],
    )

    op.drop_index("idx_query_log_org_created", table_name="query_logs")
    op.drop_index("idx_sync_job_org_status", table_name="sync_jobs")
    op.drop_index("idx_api_key_org_revoked", table_name="api_keys")
    op.drop_index("idx_document_org_status", table_name="documents")
    op.drop_index("idx_connection_org_status", table_name="connections")
