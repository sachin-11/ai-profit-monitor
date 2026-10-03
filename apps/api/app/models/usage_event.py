from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.event_cost import EventCost
    from app.models.project import Project


class EventStatus(str, enum.Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class UsageEvent(Base):
    __tablename__ = "usage_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            ondelete="CASCADE",
            name="fk_usage_events_project_tenant",
        ),
        UniqueConstraint("project_id", "client_event_id", name="uq_usage_events_project_client_id"),
        CheckConstraint(
            "input_tokens BETWEEN 0 AND 1000000000 "
            "AND output_tokens BETWEEN 0 AND 1000000000 "
            "AND cached_input_tokens BETWEEN 0 AND 1000000000 "
            "AND reasoning_tokens BETWEEN 0 AND 1000000000 "
            "AND (provider_reported_total_tokens IS NULL OR "
            "provider_reported_total_tokens BETWEEN 0 AND 1000000000) "
            "AND (duration_ms IS NULL OR duration_ms BETWEEN 0 AND 86400000)",
            name="ck_usage_events_nonnegative_counts",
        ),
        CheckConstraint("schema_version IN (1, 2)", name="ck_usage_events_schema_version"),
        CheckConstraint(
            "schema_version <> 2 OR (cached_input_tokens <= input_tokens "
            "AND reasoning_tokens <= output_tokens)",
            name="ck_usage_events_token_subsets",
        ),
        Index("ix_usage_events_project_occurred", "project_id", "occurred_at", "id"),
        Index("ix_usage_events_organization_occurred", "organization_id", "occurred_at"),
        Index(
            "ix_usage_events_project_customer_occurred",
            "project_id",
            "customer_external_id",
            "occurred_at",
        ),
        Index("ix_usage_events_project_feature_occurred", "project_id", "feature", "occurred_at"),
        Index(
            "ix_usage_events_project_provider_model_occurred",
            "project_id",
            "provider",
            "model",
            "occurred_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    client_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[int] = mapped_column(nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    customer_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    feature: Mapped[str] = mapped_column(String(100), nullable=False)
    operation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[EventStatus] = mapped_column(
        Enum(
            EventStatus,
            name="usage_event_status",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    output_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cached_input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reasoning_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    provider_reported_total_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tags: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    payload_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="events")
    cost: Mapped[EventCost | None] = relationship(
        back_populates="usage_event",
        uselist=False,
        lazy="raise",
        passive_deletes=True,
    )
