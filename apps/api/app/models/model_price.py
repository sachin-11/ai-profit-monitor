from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Index,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ReasoningBillingMode(str, enum.Enum):
    INCLUDED_IN_OUTPUT = "included_in_output"
    SEPARATELY_PRICED = "separately_priced"
    NOT_SUPPORTED = "not_supported"


class ModelPrice(Base):
    __tablename__ = "model_prices"
    __table_args__ = (
        CheckConstraint(
            "provider = lower(btrim(provider)) AND provider ~ '^[a-z][a-z0-9_]+$' "
            "AND model = lower(btrim(model)) AND length(model) > 0",
            name="ck_model_prices_normalized_names",
        ),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_model_prices_currency"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from", name="ck_model_prices_interval"
        ),
        CheckConstraint(
            "input_price_per_million BETWEEN 0 AND 1000000000 "
            "AND output_price_per_million BETWEEN 0 AND 1000000000 "
            "AND (cached_input_price_per_million IS NULL OR "
            "cached_input_price_per_million BETWEEN 0 AND 1000000000) "
            "AND (reasoning_price_per_million IS NULL OR "
            "reasoning_price_per_million BETWEEN 0 AND 1000000000)",
            name="ck_model_prices_rates",
        ),
        CheckConstraint(
            "(reasoning_billing_mode = 'separately_priced' "
            "AND reasoning_price_per_million IS NOT NULL) OR "
            "(reasoning_billing_mode <> 'separately_priced' "
            "AND reasoning_price_per_million IS NULL)",
            name="ck_model_prices_reasoning_rate",
        ),
        ExcludeConstraint(  # type: ignore[no-untyped-call]
            ("provider", "="),
            ("model", "="),
            ("currency", "="),
            (func.tstzrange(text("effective_from"), text("effective_to"), "[)"), "&&"),
            where=text("is_active"),
            using="gist",
            name="ex_model_prices_active_interval",
        ),
        Index("ix_model_prices_lookup", "provider", "model", "currency", "effective_from"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    input_price_per_million: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    cached_input_price_per_million: Mapped[Decimal | None] = mapped_column(Numeric(24, 12))
    output_price_per_million: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    reasoning_price_per_million: Mapped[Decimal | None] = mapped_column(Numeric(24, 12))
    reasoning_billing_mode: Mapped[ReasoningBillingMode] = mapped_column(
        Enum(
            ReasoningBillingMode,
            name="reasoning_billing_mode",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048))
    source_retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    catalog_version: Mapped[str] = mapped_column(String(100), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
