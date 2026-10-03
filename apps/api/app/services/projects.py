from __future__ import annotations

import re
import secrets
import unicodedata
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.models.project import Project, ProjectEnvironment
from app.schemas.project import ProjectUpdate


def project_slug(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return (re.sub(r"[^a-z0-9]+", "-", ascii_name.casefold()).strip("-") or "project")[:100]


async def list_projects(db: AsyncSession, organization_id: uuid.UUID) -> list[Project]:
    result = await db.scalars(
        select(Project)
        .where(Project.organization_id == organization_id)
        .order_by(Project.created_at.desc(), Project.id.desc())
    )
    return list(result.all())


async def create_project(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    name: str,
    environment: ProjectEnvironment,
    description: str | None,
) -> Project:
    base_slug = project_slug(name)
    for attempt in range(5):
        candidate = base_slug if attempt == 0 else f"{base_slug}-{secrets.token_hex(3)}"
        project_id = uuid.uuid4()
        statement = (
            insert(Project)
            .values(
                id=project_id,
                organization_id=organization_id,
                name=name,
                slug=candidate,
                environment=environment,
                description=description,
                is_active=True,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(constraint="uq_projects_organization_slug")
            .returning(Project.id)
        )
        inserted_id = await db.scalar(statement)
        if inserted_id is not None:
            await db.commit()
            project = await db.get(Project, inserted_id)
            assert project is not None
            return project
    await db.rollback()
    raise ApiError(409, "project_slug_conflict", "Could not create the project")


async def update_project(db: AsyncSession, project: Project, payload: ProjectUpdate) -> Project:
    if "name" in payload.model_fields_set:
        if payload.name is None:
            raise ApiError(422, "invalid_project", "Project name cannot be null")
        project.name = payload.name
    if "description" in payload.model_fields_set:
        project.description = payload.description
    if "is_active" in payload.model_fields_set:
        if payload.is_active is None:
            raise ApiError(422, "invalid_project", "Project active status cannot be null")
        project.is_active = payload.is_active
    # The slug remains stable after renaming to preserve existing references.
    await db.commit()
    await db.refresh(project)
    return project
