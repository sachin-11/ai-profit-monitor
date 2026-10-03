from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.membership import MembershipRole


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    display_name: str
    is_active: bool
    created_at: datetime


class OrganizationPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime


class MembershipPublic(BaseModel):
    id: uuid.UUID
    role: MembershipRole
    created_at: datetime
    organization: OrganizationPublic


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=1024)
    display_name: str = Field(min_length=1, max_length=100)
    organization_name: str = Field(min_length=1, max_length=120)

    @field_validator("display_name", "organization_name")
    @classmethod
    def strip_nonempty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class RegisterData(BaseModel):
    user: UserPublic
    organization: OrganizationPublic
    membership: MembershipPublic


class LoginData(BaseModel):
    user: UserPublic


class MeData(BaseModel):
    user: UserPublic
    memberships: list[MembershipPublic]


class LogoutData(BaseModel):
    logged_out: bool = True
