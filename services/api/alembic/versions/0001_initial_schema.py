"""Initial schema — all Nexus tables

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── organizations ──────────────────────────────────────────────────────
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("plan", sa.String(50), nullable=False, server_default="starter"),
        sa.Column("doc_limit", sa.Integer, nullable=False, server_default="50000"),
        sa.Column("query_limit_monthly", sa.Integer, nullable=False, server_default="5000"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── connections ────────────────────────────────────────────────────────
    op.create_table(
        "connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("connector_id", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("scopes", postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column("webhook_sub_id", sa.String(255), nullable=True),
        sa.Column("webhook_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("connector_metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "uq_connection_org_connector", "connections", ["org_id", "connector_id"], unique=True
    )

    # ── oauth_credentials ──────────────────────────────────────────────────
    op.create_table(
        "oauth_credentials",
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("connections.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("access_token_enc", sa.LargeBinary, nullable=False),
        sa.Column("refresh_token_enc", sa.LargeBinary, nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("kms_key_id", sa.String(255), nullable=False),
        sa.Column("token_metadata", postgresql.JSONB, nullable=False, server_default="{}"),
    )

    # ── documents ──────────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(512), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("source_url", sa.Text, nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("chunk_count", sa.Integer, server_default="0"),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acl", postgresql.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("connector_metadata", postgresql.JSONB, nullable=False, server_default="{}"),
    )
    op.create_index(
        "uq_document_org_conn_ext",
        "documents",
        ["org_id", "connection_id", "external_id"],
        unique=True,
    )
    op.create_index("idx_document_org", "documents", ["org_id"])
    op.create_index("idx_document_connection", "documents", ["connection_id"])
    op.create_index("idx_document_status", "documents", ["status"])

    # ── api_keys ───────────────────────────────────────────────────────────
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("key_prefix", sa.String(12), nullable=False),
        sa.Column("scopes", postgresql.ARRAY(sa.Text), nullable=False, server_default="{query}"),
        sa.Column("rate_limit_rpm", sa.Integer, nullable=False, server_default="60"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── sync_jobs ──────────────────────────────────────────────────────────
    op.create_table(
        "sync_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("job_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("docs_processed", sa.Integer, server_default="0"),
        sa.Column("docs_total", sa.Integer, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text, nullable=True),
    )
    op.create_index("idx_sync_job_connection", "sync_jobs", ["connection_id"])

    # ── query_logs ─────────────────────────────────────────────────────────
    op.create_table(
        "query_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "api_key_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("api_keys.id"), nullable=True
        ),
        sa.Column("query_hash", sa.String(64), nullable=False),
        sa.Column("response_tokens", sa.Integer, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("source_count", sa.Integer, server_default="0"),
        sa.Column("cached", sa.Boolean, server_default="false"),
        sa.Column(
            "connectors_used", postgresql.ARRAY(sa.Text), nullable=False, server_default="{}"
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_query_log_org", "query_logs", ["org_id"])


def downgrade() -> None:
    op.drop_table("query_logs")
    op.drop_table("sync_jobs")
    op.drop_table("api_keys")
    op.drop_table("documents")
    op.drop_table("oauth_credentials")
    op.drop_table("connections")
    op.drop_table("organizations")
