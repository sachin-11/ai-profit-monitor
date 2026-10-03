from __future__ import annotations

import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.api.dependencies import CurrentAuth, DatabaseSession, get_request_settings
from app.core.errors import ApiError
from app.models.membership import Membership, MembershipRole
from app.models.project import Project
from app.models.project_api_key import ProjectApiKey
from app.services.project_api_keys import hash_api_key

KEY_PATTERN = re.compile(
    r"^aipm_(development|staging|production)_([0-9a-f]{16})_([A-Za-z0-9_-]{43})$"
)


@dataclass(frozen=True)
class ProjectMemberContext:
    project: Project
    membership: Membership


@dataclass(frozen=True)
class IngestionProjectContext:
    project: Project
    api_key: ProjectApiKey


async def require_project_member(
    project_id: uuid.UUID,
    auth: CurrentAuth,
    db: DatabaseSession,
) -> ProjectMemberContext:
    row = (
        await db.execute(
            select(Project, Membership)
            .join(
                Membership,
                Membership.organization_id == Project.organization_id,
            )
            .where(Project.id == project_id, Membership.user_id == auth.user.id)
        )
    ).first()
    if row is None:
        raise ApiError(404, "not_found", "Project not found")
    return ProjectMemberContext(project=row[0], membership=row[1])


ProjectMember = Annotated[ProjectMemberContext, Depends(require_project_member)]


async def require_project_admin(context: ProjectMember) -> ProjectMemberContext:
    if context.membership.role not in {MembershipRole.OWNER, MembershipRole.ADMIN}:
        raise ApiError(403, "forbidden", "Owner or admin role required")
    return context


ProjectAdmin = Annotated[ProjectMemberContext, Depends(require_project_admin)]


async def require_ingestion_project(
    request: Request,
    db: DatabaseSession,
) -> IngestionProjectContext:
    authorization = request.headers.get("authorization", "")
    scheme, _, raw_key = authorization.partition(" ")
    if scheme.lower() != "bearer" or not raw_key or " " in raw_key:
        raise ApiError(401, "invalid_api_key", "Invalid API key")
    match = KEY_PATTERN.fullmatch(raw_key)
    if match is None:
        raise ApiError(401, "invalid_api_key", "Invalid API key")

    key = await db.scalar(
        select(ProjectApiKey)
        .options(joinedload(ProjectApiKey.project))
        .where(ProjectApiKey.key_prefix == match.group(2))
    )
    now = datetime.now(UTC)
    if (
        key is None
        or not secrets.compare_digest(key.key_hash, hash_api_key(raw_key))
        or key.project.environment.value != match.group(1)
        or key.revoked_at is not None
        or (key.expires_at is not None and key.expires_at <= now)
    ):
        raise ApiError(401, "invalid_api_key", "Invalid API key")
    if not key.project.is_active:
        raise ApiError(403, "project_inactive", "Project is inactive")

    settings = get_request_settings(request)
    refresh_before = now - timedelta(seconds=settings.api_key_last_used_update_seconds)
    if key.last_used_at is None or key.last_used_at <= refresh_before:
        key.last_used_at = now
        await db.commit()
    return IngestionProjectContext(project=key.project, api_key=key)


IngestionProject = Annotated[IngestionProjectContext, Depends(require_ingestion_project)]
