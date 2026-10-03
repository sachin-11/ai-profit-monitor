from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.membership import Membership, MembershipRole
from app.models.organization import Organization
from app.models.session import AuthSession
from app.models.user import User

PASSWORD = "a-secure-passphrase"
ORIGIN = {"Origin": "http://localhost:3000"}


async def register(
    client: AsyncClient,
    *,
    email: str = "owner@example.com",
    display_name: str = "Owner User",
    organization_name: str = "Acme AI",
) -> Any:
    return await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "display_name": display_name,
            "organization_name": organization_name,
        },
        headers=ORIGIN,
    )


async def login(client: AsyncClient, email: str, password: str = PASSWORD) -> Any:
    return await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers=ORIGIN,
    )


async def test_registration_creates_user_organization_owner_and_session_hash(
    client: AsyncClient, db: AsyncSession
) -> None:
    response = await register(client)

    assert response.status_code == 201
    payload = response.json()["data"]
    assert payload["user"]["email"] == "owner@example.com"
    assert payload["organization"]["name"] == "Acme AI"
    assert payload["membership"]["role"] == "owner"
    assert "password_hash" not in response.text
    assert "token_hash" not in response.text

    user = await db.scalar(select(User).where(User.normalized_email == "owner@example.com"))
    organization = await db.scalar(select(Organization))
    membership = await db.scalar(select(Membership))
    stored_session = await db.scalar(select(AuthSession))
    assert user is not None and organization is not None and membership is not None
    assert membership.user_id == user.id
    assert membership.organization_id == organization.id
    assert membership.role is MembershipRole.OWNER
    assert stored_session is not None
    raw_cookie = client.cookies.get("ai_profit_monitor_session")
    assert raw_cookie is not None
    assert stored_session.token_hash != raw_cookie
    assert len(stored_session.token_hash) == 64
    assert "domain=" not in response.headers["set-cookie"].lower()


async def test_duplicate_email_is_rejected_without_partial_tenant_data(
    client: AsyncClient, db: AsyncSession
) -> None:
    assert (await register(client)).status_code == 201
    response = await register(
        client,
        email="OWNER@example.com",
        organization_name="Should Not Exist",
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_already_registered"
    assert await db.scalar(select(func.count()).select_from(User)) == 1
    assert await db.scalar(select(func.count()).select_from(Organization)) == 1
    assert await db.scalar(select(func.count()).select_from(Membership)) == 1


async def test_login_success_and_failures_are_generic(client: AsyncClient) -> None:
    await register(client)
    client.cookies.clear()

    success = await login(client, "OWNER@example.com")
    assert success.status_code == 200
    assert success.json()["data"]["user"]["display_name"] == "Owner User"

    unknown = await login(client, "missing@example.com")
    incorrect = await login(client, "owner@example.com", "incorrect-password")
    assert unknown.status_code == incorrect.status_code == 401
    assert unknown.json() == incorrect.json()
    assert unknown.json()["error"]["message"] == "Invalid email or password"


async def test_me_requires_authentication_and_returns_safe_memberships(
    client: AsyncClient,
) -> None:
    unauthenticated = await client.get("/api/v1/auth/me")
    assert unauthenticated.status_code == 401

    await register(client)
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["user"]["email"] == "owner@example.com"
    assert data["memberships"][0]["organization"]["name"] == "Acme AI"
    assert "password" not in response.text
    assert "token" not in response.text


async def test_logout_is_idempotent_and_revokes_session(
    client: AsyncClient, db: AsyncSession
) -> None:
    await register(client)
    raw_token = client.cookies.get("ai_profit_monitor_session")
    assert raw_token is not None
    response = await client.post("/api/v1/auth/logout", headers=ORIGIN)
    assert response.status_code == 200
    assert await db.scalar(select(func.count()).select_from(AuthSession)) == 0

    client.cookies.set("ai_profit_monitor_session", raw_token)
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    assert (await client.post("/api/v1/auth/logout", headers=ORIGIN)).status_code == 200


async def test_expired_session_is_rejected(client: AsyncClient, db: AsyncSession) -> None:
    await register(client)
    stored_session = await db.scalar(select(AuthSession))
    assert stored_session is not None
    stored_session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db.commit()

    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_organization_listing_and_cross_tenant_access(client: AsyncClient, app: Any) -> None:
    first = await register(client)
    first_id = first.json()["data"]["organization"]["id"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other:
        second = await register(
            other,
            email="other@example.com",
            display_name="Other User",
            organization_name="Other Org",
        )
        second_id = second.json()["data"]["organization"]["id"]
        listing = await other.get("/api/v1/organizations")
        assert [item["organization"]["id"] for item in listing.json()["data"]["organizations"]] == [
            second_id
        ]

    assert (await client.get(f"/api/v1/organizations/{first_id}")).status_code == 200
    denied = await client.get(f"/api/v1/organizations/{second_id}")
    assert denied.status_code == 404
    assert denied.json()["error"]["code"] == "organization_not_found"


async def test_member_cannot_update_but_admin_and_owner_can(
    client: AsyncClient, app: Any, db: AsyncSession
) -> None:
    registered = await register(client)
    organization_id = registered.json()["data"]["organization"]["id"]
    owner_update = await client.patch(
        f"/api/v1/organizations/{organization_id}",
        json={"name": "Renamed by Owner"},
        headers=ORIGIN,
    )
    assert owner_update.status_code == 200
    original_slug = owner_update.json()["data"]["organization"]["slug"]

    member = User(
        email="member@example.com",
        normalized_email="member@example.com",
        password_hash=hash_password(PASSWORD),
        display_name="Member User",
    )
    member_membership = Membership(
        user=member,
        organization_id=organization_id,
        role=MembershipRole.MEMBER,
    )
    db.add_all([member, member_membership])
    await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as member_client:
        assert (await login(member_client, "member@example.com")).status_code == 200
        denied = await member_client.patch(
            f"/api/v1/organizations/{organization_id}",
            json={"name": "Forbidden Rename"},
            headers=ORIGIN,
        )
        assert denied.status_code == 403
        member_membership.role = MembershipRole.ADMIN
        await db.commit()
        allowed = await member_client.patch(
            f"/api/v1/organizations/{organization_id}",
            json={"name": "Renamed by Admin"},
            headers=ORIGIN,
        )
        assert allowed.status_code == 200
        assert allowed.json()["data"]["organization"]["slug"] == original_slug


async def test_member_listing_is_safe(client: AsyncClient) -> None:
    registered = await register(client)
    organization_id = registered.json()["data"]["organization"]["id"]
    response = await client.get(f"/api/v1/organizations/{organization_id}/members")

    assert response.status_code == 200
    member = response.json()["data"]["members"][0]
    assert member["email"] == "owner@example.com"
    assert member["role"] == "owner"
    assert "password" not in response.text
    assert "session" not in response.text


async def test_authenticated_mutation_rejects_missing_or_untrusted_origin(
    client: AsyncClient,
) -> None:
    registered = await register(client)
    organization_id = registered.json()["data"]["organization"]["id"]
    path = f"/api/v1/organizations/{organization_id}"

    missing = await client.patch(path, json={"name": "No Origin"})
    untrusted = await client.patch(
        path,
        json={"name": "Evil Origin"},
        headers={"Origin": "https://evil.example"},
    )
    assert missing.status_code == untrusted.status_code == 403
    assert missing.json()["error"]["code"] == "untrusted_origin"
