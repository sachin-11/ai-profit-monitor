from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.membership import Membership
from app.models.user import User


async def list_memberships(db: AsyncSession, user_id: uuid.UUID) -> list[Membership]:
    result = await db.scalars(
        select(Membership)
        .options(selectinload(Membership.organization))
        .where(Membership.user_id == user_id)
        .order_by(Membership.created_at)
    )
    return list(result.all())


async def update_organization_name(
    db: AsyncSession, membership: Membership, name: str
) -> Membership:
    # Slugs are intentionally stable so existing URLs/integrations do not break on rename.
    membership.organization.name = name.strip()
    await db.commit()
    await db.refresh(membership.organization)
    return membership


async def list_organization_members(
    db: AsyncSession, organization_id: uuid.UUID
) -> list[tuple[Membership, User]]:
    rows = await db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == organization_id)
        .order_by(Membership.created_at)
    )
    return list(rows.tuples().all())
