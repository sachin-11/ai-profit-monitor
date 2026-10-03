"""Add projects, API keys, and normalized usage events.

Revision ID: 20261003_0003
Revises: 20261003_0002
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261003_0003"
down_revision: str | None = "20261003_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

project_environment = postgresql.ENUM(
    "development", "staging", "production", name="project_environment", create_type=False
)
usage_event_status = postgresql.ENUM(
    "success", "error", "timeout", "cancelled", name="usage_event_status", create_type=False
)


def upgrade() -> None:
    project_environment.create(op.get_bind(), checkfirst=True)
    usage_event_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=140), nullable=False),
        sa.Column("environment", project_environment, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_projects_organization_id",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
        sa.UniqueConstraint("organization_id", "slug", name="uq_projects_organization_slug"),
        sa.UniqueConstraint("organization_id", "id", name="uq_projects_organization_id"),
    )
    op.create_table(
        "project_api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("key_prefix", sa.String(length=16), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
            name="fk_project_api_keys_project_id",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_project_api_keys_created_by",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_project_api_keys"),
        sa.UniqueConstraint("key_prefix", name="uq_project_api_keys_key_prefix"),
        sa.UniqueConstraint("key_hash", name="uq_project_api_keys_key_hash"),
    )
    op.create_index("ix_project_api_keys_project_id", "project_api_keys", ["project_id"])
    op.create_table(
        "usage_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_event_id", sa.String(length=128), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("customer_external_id", sa.String(length=128), nullable=True),
        sa.Column("feature", sa.String(length=100), nullable=False),
        sa.Column("operation", sa.String(length=100), nullable=True),
        sa.Column("status", usage_event_status, nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False),
        sa.Column("cached_input_tokens", sa.BigInteger(), nullable=False),
        sa.Column("reasoning_tokens", sa.BigInteger(), nullable=False),
        sa.Column("provider_reported_total_tokens", sa.BigInteger(), nullable=True),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("provider_request_id", sa.String(length=128), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("tags", postgresql.JSONB(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("payload_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "input_tokens BETWEEN 0 AND 1000000000 "
            "AND output_tokens BETWEEN 0 AND 1000000000 "
            "AND cached_input_tokens BETWEEN 0 AND 1000000000 "
            "AND reasoning_tokens BETWEEN 0 AND 1000000000 "
            "AND (provider_reported_total_tokens IS NULL OR "
            "provider_reported_total_tokens BETWEEN 0 AND 1000000000) "
            "AND (duration_ms IS NULL OR duration_ms BETWEEN 0 AND 86400000)",
            name="ck_usage_events_nonnegative_counts",
        ),
        sa.CheckConstraint("schema_version = 1", name="ck_usage_events_schema_version"),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            ondelete="CASCADE",
            name="fk_usage_events_project_tenant",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_usage_events"),
        sa.UniqueConstraint(
            "project_id", "client_event_id", name="uq_usage_events_project_client_id"
        ),
    )
    op.create_index(
        "ix_usage_events_project_occurred", "usage_events", ["project_id", "occurred_at", "id"]
    )
    op.create_index(
        "ix_usage_events_organization_occurred", "usage_events", ["organization_id", "occurred_at"]
    )
    op.create_index(
        "ix_usage_events_project_customer_occurred",
        "usage_events",
        ["project_id", "customer_external_id", "occurred_at"],
    )
    op.create_index(
        "ix_usage_events_project_feature_occurred",
        "usage_events",
        ["project_id", "feature", "occurred_at"],
    )
    op.create_index(
        "ix_usage_events_project_provider_model_occurred",
        "usage_events",
        ["project_id", "provider", "model", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_usage_events_project_provider_model_occurred", table_name="usage_events")
    op.drop_index("ix_usage_events_project_feature_occurred", table_name="usage_events")
    op.drop_index("ix_usage_events_project_customer_occurred", table_name="usage_events")
    op.drop_index("ix_usage_events_organization_occurred", table_name="usage_events")
    op.drop_index("ix_usage_events_project_occurred", table_name="usage_events")
    op.drop_table("usage_events")
    op.drop_index("ix_project_api_keys_project_id", table_name="project_api_keys")
    op.drop_table("project_api_keys")
    op.drop_table("projects")
    usage_event_status.drop(op.get_bind(), checkfirst=True)
    project_environment.drop(op.get_bind(), checkfirst=True)
