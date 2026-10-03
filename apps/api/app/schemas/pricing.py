from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any
from urllib.parse import urlsplit

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from app.models.event_cost import CostStatus
from app.models.model_price import ReasoningBillingMode

Rate = Annotated[
    Decimal, Field(ge=Decimal("0"), le=Decimal("1000000000"), max_digits=24, decimal_places=12)
]
RATE_FIELDS = (
    "input_price_per_million",
    "cached_input_price_per_million",
    "output_price_per_million",
    "reasoning_price_per_million",
)


class ModelPriceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=2, max_length=40, pattern=r"^[a-z][a-z0-9_]*$")
    model: str = Field(min_length=1, max_length=120)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    input_price_per_million: Rate
    cached_input_price_per_million: Rate | None = None
    output_price_per_million: Rate
    reasoning_price_per_million: Rate | None = None
    reasoning_billing_mode: ReasoningBillingMode
    effective_from: AwareDatetime
    effective_to: AwareDatetime | None = None
    source_name: str = Field(min_length=1, max_length=200)
    source_url: str | None = Field(default=None, max_length=2048)
    source_retrieved_at: AwareDatetime | None = None
    catalog_version: str = Field(min_length=1, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)
    is_active: bool = True

    @field_validator(*RATE_FIELDS, mode="before")
    @classmethod
    def exact_rates(cls, value: Any) -> Any:
        if isinstance(value, float | bool):
            raise ValueError("rates must be decimal strings, never floating-point numbers")
        return value

    @field_validator("provider", "model", mode="before")
    @classmethod
    def normalized_name(cls, value: str) -> str:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("currency", mode="before")
    @classmethod
    def normalized_currency(cls, value: str) -> str:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("source_name", "catalog_version")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()

    @field_validator("source_url")
    @classmethod
    def safe_source_url(cls, value: str | None) -> str | None:
        if value is not None:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"https", "http"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or any(c.isspace() for c in value)
            ):
                raise ValueError("source URL must be an HTTP(S) URL without credentials")
        return value

    @field_validator("effective_from", "effective_to", "source_retrieved_at")
    @classmethod
    def utc_time(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(UTC) if value is not None else None

    @model_validator(mode="after")
    def valid_price(self) -> ModelPriceCreate:
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be later than effective_from")
        separate = self.reasoning_billing_mode == ReasoningBillingMode.SEPARATELY_PRICED
        if separate != (self.reasoning_price_per_million is not None):
            raise ValueError("only separately_priced reasoning requires a reasoning rate")
        return self


class ModelPricePublic(ModelPriceCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime

    @field_serializer(*RATE_FIELDS)
    def serialize_rate(self, value: Decimal | None) -> str | None:
        return format(value, "f") if value is not None else None


class PriceListData(BaseModel):
    prices: list[ModelPricePublic]


class CostPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    usage_event_id: uuid.UUID
    model_price_id: uuid.UUID | None
    status: CostStatus
    currency: str | None
    uncached_input_tokens: int
    cached_input_tokens: int
    regular_output_tokens: int
    reasoning_tokens: int
    uncached_input_cost: Decimal | None
    cached_input_cost: Decimal | None
    output_cost: Decimal | None
    reasoning_cost: Decimal | None
    total_cost: Decimal | None
    calculation_version: str
    calculated_at: datetime
    reason_code: str | None
    reason_detail: str | None
    created_at: datetime
    updated_at: datetime
    model_price: ModelPricePublic | None

    @field_serializer(
        "uncached_input_cost", "cached_input_cost", "output_cost", "reasoning_cost", "total_cost"
    )
    def serialize_money(self, value: Decimal | None) -> str | None:
        return format(value, "f") if value is not None else None


class RecalculateCosts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    replace_calculated: bool = False

    @field_validator("event_ids")
    @classmethod
    def unique_ids(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(value) != len(set(value)):
            raise ValueError("event IDs must be unique")
        return value


class RecalculateData(BaseModel):
    updated_count: int
    skipped_count: int
    costs: list[CostPublic]
