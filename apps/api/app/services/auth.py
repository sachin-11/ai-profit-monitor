from __future__ import annotations

import re
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.errors import ApiError
from app.core.security import (
    generate_session_token,
    hash_password,
    hash_session_token,
    normalize_email,
    verify_password,
)
from app.models.membership import Membership, MembershipRole
from app.models.organization import Organization
from app.models.session import AuthSession
from app.models.user import User


@dataclass(frozen=True)
class RegistrationResult:
    user: User
    organization: Organization
    membership: Membership
    raw_session_token: str


@dataclass(frozen=True)
class LoginResult:
    user: User
    raw_session_token: str


def _slugify(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.casefold()).strip("-")
    return (slug or "organization")[:100]


def _constraint_name(exc: IntegrityError) -> str | None:
    original = exc.orig
    name = getattr(original, "constraint_name", None)
    if isinstance(name, str):
        return name
    cause = getattr(original, "__cause__", None)
    name = getattr(cause, "constraint_name", None)
    return name if isinstance(name, str) else None


def _new_session(user: User, settings: Settings) -> tuple[AuthSession, str]:
    now = datetime.now(UTC)
    raw_token = generate_session_token()
    return (
        AuthSession(
            user=user,
            token_hash=hash_session_token(raw_token),
            created_at=now,
            last_used_at=now,
            expires_at=now + timedelta(seconds=settings.session_lifetime_seconds),
        ),
        raw_token,
    )


async def register_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    display_name: str,
    organization_name: str,
    settings: Settings,
) -> RegistrationResult:
    normalized_email = normalize_email(email)
    existing = await db.scalar(select(User.id).where(User.normalized_email == normalized_email))
    if existing is not None:
        raise ApiError(409, "email_already_registered", "An account with this email already exists")

    password_digest = hash_password(password)
    base_slug = _slugify(organization_name)
    slug = base_slug

    for attempt in range(5):
        user = User(
            email=email.strip(),
            normalized_email=normalized_email,
            password_hash=password_digest,
            display_name=display_name.strip(),
        )
        organization = Organization(name=organization_name.strip(), slug=slug)
        membership = Membership(
            user=user,
            organization=organization,
            role=MembershipRole.OWNER,
        )
        auth_session, raw_token = _new_session(user, settings)
        db.add_all([user, organization, membership, auth_session])
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            constraint = _constraint_name(exc)
            if constraint == "uq_users_normalized_email":
                raise ApiError(
                    409,
                    "email_already_registered",
                    "An account with this email already exists",
                ) from None
            if constraint == "uq_organizations_slug" and attempt < 4:
                slug = f"{base_slug}-{secrets.token_hex(3)}"
                continue
            raise
        await db.refresh(user)
        await db.refresh(organization)
        await db.refresh(membership)
        return RegistrationResult(user, organization, membership, raw_token)

    raise ApiError(409, "organization_slug_conflict", "Could not create the organization")


async def authenticate_user(
    db: AsyncSession, *, email: str, password: str, settings: Settings
) -> LoginResult | None:
    normalized_email = normalize_email(email)
    user = await db.scalar(select(User).where(User.normalized_email == normalized_email))
    password_valid = verify_password(password, user.password_hash if user is not None else None)
    if user is None or not password_valid or not user.is_active:
        return None

    auth_session, raw_token = _new_session(user, settings)
    db.add(auth_session)
    await db.commit()
    await db.refresh(user)
    return LoginResult(user=user, raw_session_token=raw_token)


async def revoke_session(db: AsyncSession, raw_token: str) -> None:
    token_hash = hash_session_token(raw_token)
    auth_session = await db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash))
    if auth_session is not None:
        await db.delete(auth_session)
        await db.commit()


async def get_user_memberships(db: AsyncSession, user_id: object) -> list[Membership]:
    result = await db.scalars(
        select(Membership)
        .options(selectinload(Membership.organization))
        .where(Membership.user_id == user_id)
        .order_by(Membership.created_at)
    )
    return list(result.all())
