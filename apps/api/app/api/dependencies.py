from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, cast
from urllib.parse import urlsplit

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.config import Settings
from app.core.errors import ApiError
from app.core.security import hash_session_token
from app.db.session import get_database_session
from app.models.membership import Membership, MembershipRole
from app.models.session import AuthSession
from app.models.user import User

DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: AuthSession


def get_request_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def _origin_from_referer(referer: str) -> str | None:
    parsed = urlsplit(referer)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def enforce_trusted_origin(request: Request) -> None:
    settings = get_request_settings(request)
    if settings.session_cookie_name not in request.cookies:
        return
    supplied_origin = request.headers.get("origin")
    if supplied_origin is None:
        referer = request.headers.get("referer")
        supplied_origin = _origin_from_referer(referer) if referer else None
    allowed = {str(origin).rstrip("/") for origin in settings.cors_origins}
    if supplied_origin is None or supplied_origin.rstrip("/") not in allowed:
        raise ApiError(403, "untrusted_origin", "Request origin is not allowed")


async def get_current_auth(
    request: Request,
    db: DatabaseSession,
) -> AuthContext:
    settings = get_request_settings(request)
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        raise ApiError(401, "authentication_required", "Authentication required")

    now = datetime.now(UTC)
    auth_session = await db.scalar(
        select(AuthSession)
        .options(joinedload(AuthSession.user))
        .where(
            AuthSession.token_hash == hash_session_token(raw_token),
            AuthSession.expires_at > now,
        )
    )
    if auth_session is None or not auth_session.user.is_active:
        raise ApiError(401, "invalid_session", "Authentication required")

    refresh_before = now - timedelta(seconds=settings.session_last_used_update_seconds)
    if auth_session.last_used_at <= refresh_before:
        auth_session.last_used_at = now
        await db.commit()
    return AuthContext(user=auth_session.user, session=auth_session)


CurrentAuth = Annotated[AuthContext, Depends(get_current_auth)]


async def require_organization_member(
    organization_id: uuid.UUID,
    auth: CurrentAuth,
    db: DatabaseSession,
) -> Membership:
    membership = await db.scalar(
        select(Membership)
        .options(joinedload(Membership.organization))
        .where(
            Membership.organization_id == organization_id,
            Membership.user_id == auth.user.id,
        )
    )
    if membership is None:
        raise ApiError(404, "organization_not_found", "Organization not found")
    return membership


OrganizationMember = Annotated[Membership, Depends(require_organization_member)]


async def require_organization_admin(
    membership: OrganizationMember,
) -> Membership:
    if membership.role not in {MembershipRole.OWNER, MembershipRole.ADMIN}:
        raise ApiError(403, "insufficient_role", "Owner or admin role required")
    return membership


OrganizationAdmin = Annotated[Membership, Depends(require_organization_admin)]


async def require_organization_owner(
    membership: OrganizationMember,
) -> Membership:
    if membership.role is not MembershipRole.OWNER:
        raise ApiError(403, "insufficient_role", "Owner role required")
    return membership


OrganizationOwner = Annotated[Membership, Depends(require_organization_owner)]
