from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.membership import Membership, MembershipRole
from app.models.project_api_key import ProjectApiKey
from app.models.usage_event import UsageEvent
from app.models.user import User

ORIGIN = {"Origin": "http://localhost:3000"}
PASSWORD = "a-secure-passphrase"


async def register(
    client: AsyncClient, email: str = "owner@example.com", organization: str = "Acme AI"
) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        headers=ORIGIN,
        json={
            "email": email,
            "password": PASSWORD,
            "display_name": "Owner",
            "organization_name": organization,
        },
    )
    assert response.status_code == 201, response.text
    return cast(str, response.json()["data"]["organization"]["id"])


async def create_project(
    client: AsyncClient, organization_id: str, name: str = "Chat Backend"
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/organizations/{organization_id}/projects",
        headers=ORIGIN,
        json={"name": name, "environment": "production", "description": "Usage metadata"},
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json()["data"]["project"])


async def create_key(client: AsyncClient, project_id: str) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/projects/{project_id}/api-keys",
        headers=ORIGIN,
        json={"name": "Backend integration"},
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json()["data"])


def event(client_event_id: str = "event-1", **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "client_event_id": client_event_id,
        "schema_version": 1,
        "provider": "openai",
        "model": "gpt-4o-mini",
        "customer_external_id": "customer-123",
        "feature": "assistant",
        "operation": "chat",
        "status": "success",
        "input_tokens": 42,
        "output_tokens": 12,
        "cached_input_tokens": 3,
        "reasoning_tokens": 0,
        "provider_reported_total_tokens": 54,
        "duration_ms": 350,
        "provider_request_id": "provider-req-1",
        "tags": {"tier": "paid"},
        "occurred_at": datetime.now(UTC).isoformat(),
    }
    data.update(overrides)
    return data


async def ingest(client: AsyncClient, raw_key: str, payload: dict[str, Any]) -> Any:
    return await client.post(
        "/api/v1/ingest/events",
        headers={"Authorization": f"Bearer {raw_key}"},
        json=payload,
    )


async def add_member(
    db: AsyncSession, organization_id: str, role: MembershipRole = MembershipRole.MEMBER
) -> None:
    user = User(
        email="member@example.com",
        normalized_email="member@example.com",
        password_hash=hash_password(PASSWORD),
        display_name="Member",
    )
    db.add(user)
    db.add(Membership(user=user, organization_id=uuid.UUID(organization_id), role=role))
    await db.commit()


async def login_member(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"email": "member@example.com", "password": PASSWORD},
    )
    assert response.status_code == 200


async def test_project_roles_slug_and_cross_tenant_access(
    client: AsyncClient, app: Any, db: AsyncSession
) -> None:
    org_id = await register(client)
    first = await create_project(client, org_id)
    second = await create_project(client, org_id)
    assert first["slug"] != second["slug"]
    assert first["organization_id"] == org_id

    await add_member(db, org_id)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as member:
        await login_member(member)
        listing = await member.get(f"/api/v1/organizations/{org_id}/projects")
        assert listing.status_code == 200
        assert len(listing.json()["data"]["projects"]) == 2
        denied = await member.post(
            f"/api/v1/organizations/{org_id}/projects",
            headers=ORIGIN,
            json={"name": "Denied", "environment": "staging"},
        )
        assert denied.status_code == 403
        denied_update = await member.patch(
            f"/api/v1/projects/{first['id']}", headers=ORIGIN, json={"name": "Denied"}
        )
        assert denied_update.status_code == 403
        assert (
            await member.post(
                f"/api/v1/projects/{first['id']}/api-keys",
                headers=ORIGIN,
                json={"name": "Denied"},
            )
        ).status_code == 403

    member_row = await db.scalar(
        select(Membership).join(User).where(User.normalized_email == "member@example.com")
    )
    assert member_row is not None
    member_row.role = MembershipRole.ADMIN
    await db.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as admin:
        await login_member(admin)
        admin_project = await create_project(admin, org_id, "Admin Project")
        assert admin_project["name"] == "Admin Project"
        assert (await create_key(admin, admin_project["id"]))["raw_key"].startswith("aipm_")

    updated = await client.patch(
        f"/api/v1/projects/{first['id']}",
        headers=ORIGIN,
        json={"name": "New Name", "is_active": False},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["project"]["slug"] == first["slug"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as outsider:
        other_org = await register(outsider, "other@example.com", "Other Org")
        assert (await outsider.get(f"/api/v1/organizations/{org_id}/projects")).status_code == 404
        assert (await outsider.get(f"/api/v1/projects/{first['id']}")).status_code == 404
        assert (await outsider.get(f"/api/v1/projects/{first['id']}/api-keys")).status_code == 404
        assert (await outsider.get(f"/api/v1/projects/{first['id']}/events")).status_code == 404
        assert other_org != org_id


async def test_api_key_is_one_time_hashed_and_revocation_is_idempotent(
    client: AsyncClient, db: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    org_id = await register(client)
    project = await create_project(client, org_id)
    created = await create_key(client, project["id"])
    raw_key = created["raw_key"]
    metadata = created["api_key"]
    assert raw_key.startswith("aipm_production_")
    assert raw_key not in str(metadata)
    stored = await db.scalar(select(ProjectApiKey).where(ProjectApiKey.id == metadata["id"]))
    assert stored is not None
    assert stored.key_hash != raw_key
    assert len(stored.key_hash) == 64
    listed = await client.get(f"/api/v1/projects/{project['id']}/api-keys")
    assert listed.status_code == 200
    assert raw_key not in listed.text
    assert stored.key_hash not in listed.text

    valid = await ingest(client, raw_key, event())
    assert valid.status_code == 201, valid.text
    invalid = await ingest(client, "aipm_production_0000000000000000_invalid", event("bad"))
    assert invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "invalid_api_key"
    assert raw_key not in caplog.text

    revoke_url = f"/api/v1/projects/{project['id']}/api-keys/{metadata['id']}/revoke"
    first_revoke = await client.post(revoke_url, headers=ORIGIN)
    second_revoke = await client.post(revoke_url, headers=ORIGIN)
    assert first_revoke.status_code == second_revoke.status_code == 200
    assert first_revoke.json()["data"]["api_key"]["revoked_at"] is not None
    assert (await ingest(client, raw_key, event("after-revoke"))).status_code == 401


async def test_expired_key_and_inactive_project_reject_ingestion(
    client: AsyncClient, db: AsyncSession
) -> None:
    org_id = await register(client)
    project = await create_project(client, org_id)
    created = await create_key(client, project["id"])
    raw_key = created["raw_key"]
    stored = await db.scalar(
        select(ProjectApiKey).where(ProjectApiKey.id == created["api_key"]["id"])
    )
    assert stored is not None
    stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db.commit()
    assert (await ingest(client, raw_key, event())).status_code == 401

    stored.expires_at = None
    await db.commit()
    disabled = await client.patch(
        f"/api/v1/projects/{project['id']}", headers=ORIGIN, json={"is_active": False}
    )
    assert disabled.status_code == 200
    rejected = await ingest(client, raw_key, event())
    assert rejected.status_code == 403
    assert rejected.json()["error"]["code"] == "project_inactive"


async def test_single_ingestion_idempotency_and_privacy(
    client: AsyncClient, db: AsyncSession
) -> None:
    org_id = await register(client)
    project = await create_project(client, org_id)
    raw_key = (await create_key(client, project["id"]))["raw_key"]
    payload = event()
    created = await ingest(client, raw_key, payload)
    repeated = await ingest(client, raw_key, payload)
    changed = await ingest(client, raw_key, {**payload, "output_tokens": 99})
    assert created.status_code == 201, created.text
    assert repeated.status_code == 200
    assert created.json()["data"]["event"]["id"] == repeated.json()["data"]["event"]["id"]
    assert repeated.json()["data"]["event"]["created"] is False
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "duplicate_event_conflict"
    assert await db.scalar(select(func.count()).select_from(UsageEvent)) == 1
    stored = await db.scalar(select(UsageEvent))
    assert stored is not None
    assert str(stored.organization_id) == org_id
    assert str(stored.project_id) == project["id"]
    assert not hasattr(stored, "cost")
    assert stored.provider_reported_total_tokens == 54


@pytest.mark.parametrize(
    "override",
    [
        {"input_tokens": -1},
        {"occurred_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()},
        {"prompt": "sensitive data"},
        {"response_body": "sensitive data"},
        {"organization_id": str(uuid.uuid4())},
        {"project_id": str(uuid.uuid4())},
        {"tags": {"prompt": "sensitive data"}},
        {"tags": {str(index): "x" for index in range(21)}},
        {"tags": {"nested": {"value": "not a string"}}},
    ],
)
async def test_invalid_or_content_fields_are_rejected(
    client: AsyncClient, db: AsyncSession, override: dict[str, Any]
) -> None:
    org_id = await register(client)
    project = await create_project(client, org_id)
    raw_key = (await create_key(client, project["id"]))["raw_key"]
    response = await ingest(client, raw_key, event(**override))
    assert response.status_code == 422
    assert await db.scalar(select(func.count()).select_from(UsageEvent)) == 0


async def test_batch_is_atomic_and_duplicate_items_are_deterministic(
    client: AsyncClient, db: AsyncSession
) -> None:
    org_id = await register(client)
    project = await create_project(client, org_id)
    raw_key = (await create_key(client, project["id"]))["raw_key"]
    headers = {"Authorization": f"Bearer {raw_key}"}
    first = event("first")
    second = event("second")
    batch = await client.post(
        "/api/v1/ingest/events/batch",
        headers=headers,
        json={"events": [first, first, second]},
    )
    assert batch.status_code == 200, batch.text
    assert batch.json()["data"]["created_count"] == 2
    assert batch.json()["data"]["existing_count"] == 1
    assert await db.scalar(select(func.count()).select_from(UsageEvent)) == 2

    conflicting = await client.post(
        "/api/v1/ingest/events/batch",
        headers=headers,
        json={"events": [event("new"), {**first, "input_tokens": 500}]},
    )
    assert conflicting.status_code == 409
    assert await db.scalar(select(func.count()).select_from(UsageEvent)) == 2
    invalid = await client.post(
        "/api/v1/ingest/events/batch",
        headers=headers,
        json={"events": [event("another"), event("bad", input_tokens=-5)]},
    )
    assert invalid.status_code == 422
    assert await db.scalar(select(func.count()).select_from(UsageEvent)) == 2
    oversized = await client.post(
        "/api/v1/ingest/events/batch",
        headers=headers,
        json={"events": [event(f"large-{index}") for index in range(101)]},
    )
    assert oversized.status_code == 413
    assert oversized.json()["error"]["code"] == "batch_too_large"


async def test_concurrent_duplicate_event_only_creates_one_row(
    client: AsyncClient, app: Any, db: AsyncSession
) -> None:
    org_id = await register(client)
    project = await create_project(client, org_id)
    raw_key = (await create_key(client, project["id"]))["raw_key"]
    payload = event("concurrent")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other:
        responses = await asyncio.gather(
            ingest(client, raw_key, payload), ingest(other, raw_key, payload)
        )
    assert sorted(response.status_code for response in responses) == [200, 201]
    assert await db.scalar(select(func.count()).select_from(UsageEvent)) == 1


async def test_event_query_filters_cursor_and_project_scope(client: AsyncClient, app: Any) -> None:
    org_id = await register(client)
    project = await create_project(client, org_id)
    other_project = await create_project(client, org_id, "Other Project")
    key = (await create_key(client, project["id"]))["raw_key"]
    other_key = (await create_key(client, other_project["id"]))["raw_key"]
    occurred_at = datetime.now(UTC)
    for index in range(3):
        payload = event(
            f"pagination-{index}",
            occurred_at=(occurred_at + timedelta(seconds=index)).isoformat(),
            provider="anthropic" if index == 2 else "openai",
        )
        assert (await ingest(client, key, payload)).status_code == 201
    foreign = await ingest(client, other_key, event("other-project"))
    assert foreign.status_code == 201
    foreign_id = foreign.json()["data"]["event"]["id"]

    first_page = await client.get(f"/api/v1/projects/{project['id']}/events?limit=2")
    assert first_page.status_code == 200, first_page.text
    assert len(first_page.json()["data"]["events"]) == 2
    cursor = first_page.json()["data"]["next_cursor"]
    assert cursor is not None
    next_page = await client.get(
        f"/api/v1/projects/{project['id']}/events", params={"limit": 2, "cursor": cursor}
    )
    assert next_page.status_code == 200
    assert len(next_page.json()["data"]["events"]) == 1
    ids = [row["id"] for row in first_page.json()["data"]["events"]]
    ids += [row["id"] for row in next_page.json()["data"]["events"]]
    assert len(set(ids)) == 3

    filtered = await client.get(
        f"/api/v1/projects/{project['id']}/events", params={"provider": "anthropic"}
    )
    assert filtered.status_code == 200
    assert len(filtered.json()["data"]["events"]) == 1
    model_filter = await client.get(
        f"/api/v1/projects/{project['id']}/events",
        params={
            "model": "gpt-4o-mini",
            "feature": "assistant",
            "status": "success",
            "customer_external_id": "customer-123",
        },
    )
    assert model_filter.status_code == 200
    assert len(model_filter.json()["data"]["events"]) == 3
    invalid_cursor = await client.get(
        f"/api/v1/projects/{project['id']}/events", params={"cursor": "%%%"}
    )
    assert invalid_cursor.status_code == 422
    assert invalid_cursor.json()["error"]["code"] == "invalid_cursor"
    invalid_range = await client.get(
        f"/api/v1/projects/{project['id']}/events",
        params={
            "start_time": "2020-01-01T00:00:00Z",
            "end_time": "2026-10-03T00:00:00Z",
        },
    )
    assert invalid_range.status_code == 422
    assert (
        await client.get(f"/api/v1/projects/{project['id']}/events/{foreign_id}")
    ).status_code == 404

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as outsider:
        await register(outsider, "other@example.com", "Other Org")
        assert (
            await outsider.get(f"/api/v1/projects/{project['id']}/events/{ids[0]}")
        ).status_code == 404
        assert (await outsider.get(f"/api/v1/projects/{project['id']}/events")).status_code == 404


async def test_member_can_read_events_and_keys_cannot_access_dashboard(
    client: AsyncClient, app: Any, db: AsyncSession
) -> None:
    org_id = await register(client)
    project = await create_project(client, org_id)
    raw_key = (await create_key(client, project["id"]))["raw_key"]
    created = await ingest(client, raw_key, event("member-readable"))
    assert created.status_code == 201
    event_id = created.json()["data"]["event"]["id"]
    await add_member(db, org_id)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as member:
        await login_member(member)
        listing = await member.get(f"/api/v1/projects/{project['id']}/events")
        assert listing.status_code == 200
        assert listing.json()["data"]["events"][0]["id"] == event_id
        assert "key_hash" not in listing.text
        detail = await member.get(f"/api/v1/projects/{project['id']}/events/{event_id}")
        assert detail.status_code == 200
        assert detail.json()["data"]["event"]["client_event_id"] == "member-readable"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as key_only:
        assert (
            await key_only.get(
                f"/api/v1/projects/{project['id']}",
                headers={"Authorization": f"Bearer {raw_key}"},
            )
        ).status_code == 401
        assert (await ingest(key_only, raw_key, event("key-only"))).status_code == 201


async def test_batch_retry_is_idempotent_and_intrababatch_conflict_rolls_back(
    client: AsyncClient, db: AsyncSession
) -> None:
    org_id = await register(client)
    project = await create_project(client, org_id)
    raw_key = (await create_key(client, project["id"]))["raw_key"]
    headers = {"Authorization": f"Bearer {raw_key}"}
    payload = {"events": [event("first"), event("second")]}
    first = await client.post("/api/v1/ingest/events/batch", headers=headers, json=payload)
    retry = await client.post("/api/v1/ingest/events/batch", headers=headers, json=payload)
    assert first.status_code == retry.status_code == 200
    assert first.json()["data"]["created_count"] == 2
    assert retry.json()["data"]["created_count"] == 0
    assert retry.json()["data"]["existing_count"] == 2
    conflicting = await client.post(
        "/api/v1/ingest/events/batch",
        headers=headers,
        json={"events": [event("same", input_tokens=1), event("same", input_tokens=2)]},
    )
    assert conflicting.status_code == 409
    assert await db.scalar(select(func.count()).select_from(UsageEvent)) == 2


async def test_no_raw_key_in_logs(client: AsyncClient, caplog: pytest.LogCaptureFixture) -> None:
    org_id = await register(client)
    project = await create_project(client, org_id)
    raw_key = (await create_key(client, project["id"]))["raw_key"]
    with caplog.at_level(logging.DEBUG, logger="app"):
        assert (await ingest(client, raw_key, event("logged"))).status_code == 201
    assert raw_key not in caplog.text


async def test_oversized_body_is_rejected_before_json_validation(client: AsyncClient) -> None:
    org_id = await register(client)
    project = await create_project(client, org_id)
    raw_key = (await create_key(client, project["id"]))["raw_key"]
    response = await ingest(client, raw_key, event(tags={"large": "x" * 1_100_000}))
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"
