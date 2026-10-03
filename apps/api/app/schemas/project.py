from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.models.project import ProjectEnvironment


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    environment: ProjectEnvironment
    description: str | None = Field(default=None, max_length=1000)

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value.strip() if value is not None else None


class ProjectPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    slug: str
    environment: ProjectEnvironment
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProjectData(BaseModel):
    project: ProjectPublic
    role: str


class ProjectListData(BaseModel):
    projects: list[ProjectPublic]
    role: str


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    expires_at: AwareDatetime | None = None

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("expires_at")
    @classmethod
    def future_expiry(cls, value: datetime | None) -> datetime | None:
        if value is not None and value <= datetime.now(UTC):
            raise ValueError("must be in the future")
        return value


class ApiKeyPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None


class ApiKeyListData(BaseModel):
    api_keys: list[ApiKeyPublic]


class ApiKeyCreatedData(BaseModel):
    api_key: ApiKeyPublic
    raw_key: str
    message: str = "Copy this key now. It cannot be retrieved later."


class ApiKeyRevokedData(BaseModel):
    api_key: ApiKeyPublic
