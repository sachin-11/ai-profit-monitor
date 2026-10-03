import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.membership import MembershipRole
from app.schemas.auth import OrganizationPublic


class OrganizationMembership(BaseModel):
    organization: OrganizationPublic
    role: MembershipRole


class OrganizationListData(BaseModel):
    organizations: list[OrganizationMembership]


class OrganizationData(BaseModel):
    organization: OrganizationPublic
    role: MembershipRole


class OrganizationUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def strip_nonempty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class MemberPublic(BaseModel):
    membership_id: uuid.UUID
    user_id: uuid.UUID
    email: EmailStr
    display_name: str
    role: MembershipRole
    joined_at: datetime


class MemberListData(BaseModel):
    members: list[MemberPublic]
