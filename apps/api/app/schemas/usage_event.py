from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.models.usage_event import EventStatus

MAX_TOKENS = 1_000_000_000
FORBIDDEN_TAG_NAMES = {
    "prompt",
    "messages",
    "input_text",
    "output_text",
    "completion",
    "response_body",
    "content",
    "document",
    "documents",
    "embedding",
    "embeddings",
}


class UsageEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_event_id: str = Field(min_length=1, max_length=128)
    schema_version: Literal[1] = 1
    provider: str = Field(min_length=2, max_length=40)
    model: str = Field(min_length=1, max_length=120)
    customer_external_id: str | None = Field(default=None, max_length=128)
    feature: str = Field(min_length=1, max_length=100)
    operation: str | None = Field(default=None, max_length=100)
    status: EventStatus
    input_tokens: int = Field(ge=0, le=MAX_TOKENS)
    output_tokens: int = Field(ge=0, le=MAX_TOKENS)
    cached_input_tokens: int = Field(default=0, ge=0, le=MAX_TOKENS)
    reasoning_tokens: int = Field(default=0, ge=0, le=MAX_TOKENS)
    provider_reported_total_tokens: int | None = Field(default=None, ge=0, le=MAX_TOKENS)
    duration_ms: int | None = Field(default=None, ge=0, le=86_400_000)
    provider_request_id: str | None = Field(default=None, max_length=128)
    error_code: str | None = Field(default=None, max_length=100)
    tags: dict[str, str] = Field(default_factory=dict)
    occurred_at: AwareDatetime

    @field_validator("provider")
    @classmethod
    def valid_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_]*", normalized):
            raise ValueError("provider must be a lowercase identifier")
        return normalized

    @field_validator("client_event_id", "model", "feature")
    @classmethod
    def required_nonblank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("tags")
    @classmethod
    def bounded_tags(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 20:
            raise ValueError("at most 20 tags are allowed")
        for key, item in value.items():
            if len(key) > 64 or not key or len(item) > 256:
                raise ValueError("tag keys and values exceed their limits")
            if key.casefold() in FORBIDDEN_TAG_NAMES:
                raise ValueError("content-related tag names are not allowed")
        return value

    @field_validator("occurred_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class UsageEventBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[UsageEventCreate] = Field(min_length=1)


class IngestResult(BaseModel):
    id: uuid.UUID
    client_event_id: str
    created: bool


class IngestData(BaseModel):
    event: IngestResult


class BatchIngestData(BaseModel):
    created_count: int
    existing_count: int
    results: list[IngestResult]


class UsageEventPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID
    client_event_id: str
    schema_version: int
    provider: str
    model: str
    customer_external_id: str | None
    feature: str
    operation: str | None
    status: EventStatus
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    reasoning_tokens: int
    provider_reported_total_tokens: int | None
    duration_ms: int | None
    provider_request_id: str | None
    error_code: str | None
    tags: dict[str, str]
    occurred_at: datetime
    received_at: datetime
    created_at: datetime


class EventListData(BaseModel):
    events: list[UsageEventPublic]
    next_cursor: str | None


class EventData(BaseModel):
    event: UsageEventPublic
