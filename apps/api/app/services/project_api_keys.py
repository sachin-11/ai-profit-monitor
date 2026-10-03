from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.models.project import Project
from app.models.project_api_key import ProjectApiKey


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


async def list_api_keys(db: AsyncSession, project_id: uuid.UUID) -> list[ProjectApiKey]:
    result = await db.scalars(
        select(ProjectApiKey)
        .where(ProjectApiKey.project_id == project_id)
        .order_by(ProjectApiKey.created_at.desc(), ProjectApiKey.id.desc())
    )
    return list(result.all())


async def create_api_key(
    db: AsyncSession,
    *,
    project: Project,
    creator_id: uuid.UUID,
    name: str,
    expires_at: datetime | None,
) -> tuple[ProjectApiKey, str]:
    for _ in range(5):
        prefix = secrets.token_hex(8)
        raw_key = f"aipm_{project.environment.value}_{prefix}_{secrets.token_urlsafe(32)}"
        key_id = uuid.uuid4()
        statement = (
            insert(ProjectApiKey)
            .values(
                id=key_id,
                project_id=project.id,
                name=name,
                key_prefix=prefix,
                key_hash=hash_api_key(raw_key),
                expires_at=expires_at,
                created_by_user_id=creator_id,
                created_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing()
            .returning(ProjectApiKey.id)
        )
        inserted_id = await db.scalar(statement)
        if inserted_id is not None:
            await db.commit()
            api_key = await db.get(ProjectApiKey, inserted_id)
            assert api_key is not None
            return api_key, raw_key
    await db.rollback()
    raise ApiError(409, "api_key_conflict", "Could not create an API key")


async def revoke_api_key(
    db: AsyncSession, *, project_id: uuid.UUID, key_id: uuid.UUID
) -> ProjectApiKey:
    api_key = await db.scalar(
        select(ProjectApiKey).where(
            ProjectApiKey.id == key_id,
            ProjectApiKey.project_id == project_id,
        )
    )
    if api_key is None:
        raise ApiError(404, "not_found", "API key not found")
    if api_key.revoked_at is None:
        api_key.revoked_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(api_key)
    return api_key
