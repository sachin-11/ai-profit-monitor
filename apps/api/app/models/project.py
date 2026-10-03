from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, String, Text, UniqueConstraint, true
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.project_api_key import ProjectApiKey
    from app.models.usage_event import UsageEvent


class ProjectEnvironment(str, enum.Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_projects_organization_slug"),
        UniqueConstraint("organization_id", "id", name="uq_projects_organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), nullable=False)
    environment: Mapped[ProjectEnvironment] = mapped_column(
        Enum(
            ProjectEnvironment,
            name="project_environment",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )

    organization: Mapped[Organization] = relationship(back_populates="projects")
    api_keys: Mapped[list[ProjectApiKey]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    events: Mapped[list[UsageEvent]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
