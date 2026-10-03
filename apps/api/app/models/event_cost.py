from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.model_price import ModelPrice

if TYPE_CHECKING:
    from app.models.usage_event import UsageEvent


class CostStatus(str, enum.Enum):
    CALCULATED = "calculated"
    UNPRICED = "unpriced"
    UNSUPPORTED = "unsupported"
    INVALID = "invalid"


class EventCost(TimestampMixin, Base):
    __tablename__ = "event_costs"
    __table_args__ = (
        CheckConstraint(
            "uncached_input_tokens >= 0 AND cached_input_tokens >= 0 "
            "AND regular_output_tokens >= 0 AND reasoning_tokens >= 0",
            name="ck_event_costs_counts",
        ),
        CheckConstraint(
            "currency IS NULL OR currency ~ '^[A-Z]{3}$'", name="ck_event_costs_currency"
        ),
        CheckConstraint(
            "(status = 'calculated' AND model_price_id IS NOT NULL AND currency IS NOT NULL "
            "AND reason_code IS NULL AND reason_detail IS NULL "
            "AND uncached_input_cost IS NOT NULL AND uncached_input_cost >= 0 "
            "AND cached_input_cost IS NOT NULL AND cached_input_cost >= 0 "
            "AND output_cost IS NOT NULL AND output_cost >= 0 "
            "AND reasoning_cost IS NOT NULL AND reasoning_cost >= 0 "
            "AND total_cost IS NOT NULL AND total_cost >= 0 AND total_cost < 'Infinity'::numeric "
            "AND total_cost = uncached_input_cost + cached_input_cost "
            "+ output_cost + reasoning_cost) "
            "OR (status <> 'calculated' AND total_cost IS NULL "
            "AND uncached_input_cost IS NULL AND cached_input_cost IS NULL "
            "AND output_cost IS NULL AND reasoning_cost IS NULL AND reason_code IS NOT NULL)",
            name="ck_event_costs_result",
        ),
        Index("ix_event_costs_status", "status"),
        Index("ix_event_costs_model_price_id", "model_price_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usage_event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usage_events.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    model_price_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("model_prices.id", ondelete="RESTRICT"),
        nullable=True,
    )
    status: Mapped[CostStatus] = mapped_column(
        Enum(
            CostStatus,
            name="event_cost_status",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    currency: Mapped[str | None] = mapped_column(String(3))
    uncached_input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cached_input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    regular_output_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reasoning_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uncached_input_cost: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    cached_input_cost: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    output_cost: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    reasoning_cost: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    total_cost: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    calculation_version: Mapped[str] = mapped_column(String(40), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(80))
    reason_detail: Mapped[str | None] = mapped_column(String(300))

    usage_event: Mapped[UsageEvent] = relationship(back_populates="cost")
    model_price: Mapped[ModelPrice | None] = relationship(lazy="raise")
