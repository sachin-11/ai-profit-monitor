from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from test_projects_and_ingestion import (
    ORIGIN,
    add_member,
    create_key,
    create_project,
    event,
    ingest,
    login_member,
    register,
)

from app.core.errors import ApiError
from app.models.event_cost import CostStatus, EventCost
from app.models.model_price import ModelPrice
from app.models.usage_event import UsageEvent
from app.schemas.pricing import ModelPriceCreate
from app.schemas.usage_event import UsageEventCreate
from app.services.costs import calculate_cost, create_event_costs
from app.services.pricing import import_prices, retire_price


def price_input(**changes: Any) -> ModelPriceCreate:
    return ModelPriceCreate.model_validate(
        {
            "provider": "example",
            "model": "demo-text",
            "currency": "USD",
            "input_price_per_million": "2",
            "cached_input_price_per_million": "0.5",
            "output_price_per_million": "4",
            "reasoning_price_per_million": "6",
            "reasoning_billing_mode": "separately_priced",
            "effective_from": datetime.now(UTC) - timedelta(days=30),
            "source_name": "Synthetic test fixture, not provider pricing",
            "catalog_version": "test-v1",
            **changes,
        }
    )


def normalized_event(client_event_id: str = "priced", **changes: Any) -> dict[str, Any]:
    return event(
        client_event_id,
        **{
            "schema_version": 2,
            "provider": "example",
            "model": "DEMO-TEXT",
            "input_tokens": 1000,
            "cached_input_tokens": 200,
            "output_tokens": 500,
            "reasoning_tokens": 100,
            **changes,
        },
    )


def transient_event(**changes: Any) -> UsageEvent:
    return UsageEvent(
        id=uuid.uuid4(),
        **UsageEventCreate.model_validate(
            normalized_event(**changes),
        ).model_dump(),
    )


def transient_price(**changes: Any) -> ModelPrice:
    return ModelPrice(id=uuid.uuid4(), **price_input(**changes).model_dump())


@pytest.mark.parametrize(
    "mode,rate,expected",
    [
        ("separately_priced", "6", "0.0039"),
        ("included_in_output", None, "0.0037"),
    ],
)
def test_exact_decimal_formula_without_double_charging(
    mode: str, rate: str | None, expected: str
) -> None:
    with localcontext() as context:
        context.prec = 3  # Calculation must not inherit an unsafe ambient context.
        result = calculate_cost(
            transient_event(),
            transient_price(
                reasoning_billing_mode=mode,
                reasoning_price_per_million=rate,
            ),
            "USD",
        )
    assert result["status"] == CostStatus.CALCULATED
    assert result["uncached_input_tokens"] == 800
    assert result["regular_output_tokens"] == 400
    assert result["uncached_input_cost"] == Decimal("0.0016")
    assert result["cached_input_cost"] == Decimal("0.0001")
    assert result["output_cost"] == Decimal("0.0016")
    assert result["total_cost"] == Decimal(expected)
    assert isinstance(result["total_cost"], Decimal)


def test_tiny_cost_zero_cost_and_provider_total_are_distinct() -> None:
    row = transient_event(
        input_tokens=1,
        cached_input_tokens=0,
        output_tokens=0,
        reasoning_tokens=0,
        provider_reported_total_tokens=999999,
    )
    price = transient_price(input_price_per_million="0.000000000001")
    assert calculate_cost(row, price, "USD")["total_cost"] == Decimal("0.000000000000000001")
    zero = transient_price(input_price_per_million="0")
    assert calculate_cost(row, zero, "USD")["total_cost"] == Decimal("0")
    missing = calculate_cost(row, None, "USD")
    assert missing["status"] == CostStatus.UNPRICED
    assert missing["total_cost"] is None


@pytest.mark.parametrize(
    "changes,price_changes,reason",
    [
        ({"schema_version": 1}, {}, "legacy_token_semantics"),
        ({"operation": "image_generation"}, {}, "unsupported_operation"),
        ({"tags": {"modality": "audio"}}, {}, "unsupported_pricing_dimension"),
        ({"tags": {"cache_write_tokens": "100"}}, {}, "unsupported_pricing_dimension"),
        ({"tags": {"batch": "true"}}, {}, "unsupported_pricing_dimension"),
        ({}, {"cached_input_price_per_million": None}, "cached_input_rate_missing"),
        (
            {},
            {"reasoning_billing_mode": "not_supported", "reasoning_price_per_million": None},
            "reasoning_not_supported",
        ),
    ],
)
def test_unsupported_or_missing_dimensions_never_claim_zero(
    changes: dict[str, Any],
    price_changes: dict[str, Any],
    reason: str,
) -> None:
    result = calculate_cost(transient_event(**changes), transient_price(**price_changes), "USD")
    assert result["reason_code"] == reason
    assert result["total_cost"] is None
    assert result["uncached_input_cost"] is None


def test_no_cached_tokens_do_not_require_a_cached_rate() -> None:
    result = calculate_cost(
        transient_event(cached_input_tokens=0),
        transient_price(
            cached_input_price_per_million=None,
        ),
        "USD",
    )
    assert result["status"] == CostStatus.CALCULATED
    assert result["cached_input_cost"] == Decimal("0")


def test_invalid_internal_counts_have_an_explicit_nonmonetary_result() -> None:
    row = transient_event()
    row.cached_input_tokens = row.input_tokens + 1
    result = calculate_cost(row, transient_price(), "USD")
    assert result["status"] == CostStatus.INVALID
    assert result["total_cost"] is None


@pytest.mark.parametrize(
    "changes",
    [
        {"input_price_per_million": -1},
        {"input_price_per_million": 0.1},
        {"input_price_per_million": "NaN"},
        {"output_price_per_million": "Infinity"},
        {"input_price_per_million": "0.0000000000001"},
        {"currency": "US"},
        {"effective_to": datetime.now(UTC) - timedelta(days=40)},
        {"effective_from": datetime(2026, 1, 1)},
        {"reasoning_price_per_million": None},
        {"reasoning_billing_mode": "included_in_output"},
        {"source_url": "https://user:password@example.com/prices"},
    ],
)
def test_catalog_validation_rejects_ambiguous_or_lossy_rates(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        price_input(**changes)


async def setup_project(client: AsyncClient) -> tuple[str, str]:
    organization_id = await register(client)
    project = await create_project(client, organization_id)
    return project["id"], (await create_key(client, project["id"]))["raw_key"]


async def test_ingestion_stores_one_precise_auditable_cost_and_preserves_retries(
    client: AsyncClient,
    db: AsyncSession,
    app: Any,
) -> None:
    price = (await import_prices(db, [price_input()]))[0]
    project_id, key = await setup_project(client)
    payload = normalized_event()
    first = await ingest(client, key, payload)
    assert first.status_code == 201
    event_id = first.json()["data"]["event"]["id"]
    detail = await client.get(f"/api/v1/projects/{project_id}/events/{event_id}")
    cost = detail.json()["data"]["event"]["cost"]
    assert cost["status"] == "calculated"
    assert cost["model_price_id"] == str(price.id)
    assert cost["total_cost"] == "0.003900000000000000"
    assert cost["model_price"]["input_price_per_million"] == "2.000000000000"
    assert cost["model_price"]["source_name"].startswith("Synthetic")
    assert cost["calculation_version"] == "text_tokens_v1"
    assert cost["calculated_at"]
    retry = await ingest(client, key, payload)
    assert retry.status_code == 200
    assert (await ingest(client, key, {**payload, "input_tokens": 1001})).status_code == 409
    assert await db.scalar(select(func.count()).select_from(EventCost)) == 1
    after = await client.get(f"/api/v1/projects/{project_id}/events/{event_id}")
    assert after.json()["data"]["event"]["cost"] == cost
    listing = await client.get(f"/api/v1/projects/{project_id}/events")
    assert listing.json()["data"]["events"][0]["cost"] == cost
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous:
        assert (await anonymous.get("/api/v1/pricing/models")).status_code == 401
    catalog = await client.get(
        "/api/v1/pricing/models", params={"provider": "EXAMPLE", "model": "Demo-Text"}
    )
    assert catalog.status_code == 200
    assert catalog.json()["data"]["prices"][0]["id"] == str(price.id)
    assert (await client.post("/api/v1/pricing/models", headers=ORIGIN, json={})).status_code == 405


async def test_effective_time_boundary_exact_case_normalized_names_and_currency(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    boundary = datetime.now(UTC) - timedelta(days=1)
    old = (await import_prices(db, [price_input()]))[0]
    new = (
        await import_prices(
            db,
            [
                price_input(
                    effective_from=boundary,
                    input_price_per_million="9",
                    catalog_version="test-v2",
                )
            ],
            close_previous=True,
        )
    )[0]
    await db.refresh(old)
    assert old.effective_to == boundary
    project_id, key = await setup_project(client)
    cases = [
        ("before", {"occurred_at": (boundary - timedelta(microseconds=1)).isoformat()}, old.id),
        ("at", {"occurred_at": boundary.isoformat()}, new.id),
        ("alias", {"model": "demo-text-latest"}, None),
        ("unknown", {"model": "unknown-model"}, None),
    ]
    for name, changes, expected_price in cases:
        response = await ingest(client, key, normalized_event(name, **changes))
        event_id = response.json()["data"]["event"]["id"]
        detail = await client.get(f"/api/v1/projects/{project_id}/events/{event_id}")
        cost = detail.json()["data"]["event"]["cost"]
        assert cost["model_price_id"] == (str(expected_price) if expected_price else None)
        assert cost["status"] == ("calculated" if expected_price else "unpriced")
    await import_prices(db, [price_input(model="eur-only", currency="EUR")])
    response = await ingest(client, key, normalized_event("currency", model="eur-only"))
    event_id = response.json()["data"]["event"]["id"]
    detail = await client.get(f"/api/v1/projects/{project_id}/events/{event_id}")
    assert detail.json()["data"]["event"]["cost"]["reason_code"] == "price_not_found"


async def test_database_rejects_overlaps_immutable_rates_and_invalid_intervals(
    db: AsyncSession,
) -> None:
    price = (await import_prices(db, [price_input()]))[0]
    with pytest.raises(ApiError, match="Pricing overlaps"):
        await import_prices(db, [price_input(catalog_version="overlap")])
    await db.refresh(price)
    price.input_price_per_million = Decimal("99")
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()
    bad = ModelPrice(**price_input(model="invalid").model_dump())
    bad.effective_to = bad.effective_from
    db.add(bad)
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()
    assert await db.scalar(select(func.count()).select_from(ModelPrice)) == 1


async def test_concurrent_raw_inserts_cannot_create_overlapping_prices(
    test_engine: AsyncEngine,
) -> None:
    maker = async_sessionmaker(test_engine, expire_on_commit=False)
    payload = price_input().model_dump()

    async def insert_price() -> str:
        async with maker() as session:
            session.add(ModelPrice(**payload))
            try:
                await session.commit()
                return "created"
            except IntegrityError:
                await session.rollback()
                return "rejected"

    assert sorted(await asyncio.gather(insert_price(), insert_price())) == ["created", "rejected"]


async def test_v2_subset_validation_preserves_legacy_retry_fingerprints(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await import_prices(db, [price_input()])
    project_id, key = await setup_project(client)
    for field in ["cached_input_tokens", "reasoning_tokens"]:
        response = await ingest(client, key, normalized_event(field, **{field: 2000}))
        assert response.status_code == 422
    legacy = normalized_event("legacy", schema_version=1, cached_input_tokens=2000)
    first = await ingest(client, key, legacy)
    assert first.status_code == 201
    retry = await ingest(client, key, legacy)
    assert retry.status_code == 200
    assert retry.json()["data"]["event"]["id"] == first.json()["data"]["event"]["id"]
    listing = await client.get(f"/api/v1/projects/{project_id}/events")
    assert listing.json()["data"]["events"][0]["cost"]["reason_code"] == "legacy_token_semantics"
    assert await db.scalar(select(func.count()).select_from(UsageEvent)) == 1


async def test_batch_costs_are_atomic_and_concurrent_retries_do_not_duplicate(
    client: AsyncClient,
    db: AsyncSession,
    app: Any,
) -> None:
    await import_prices(db, [price_input()])
    _, key = await setup_project(client)
    payload = normalized_event("concurrent")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other:
        results = await asyncio.gather(ingest(client, key, payload), ingest(other, key, payload))
    assert sorted(result.status_code for result in results) == [200, 201]
    assert await db.scalar(select(func.count()).select_from(EventCost)) == 1
    headers = {"Authorization": f"Bearer {key}"}
    conflict = await client.post(
        "/api/v1/ingest/events/batch",
        headers=headers,
        json={
            "events": [normalized_event("new"), {**payload, "input_tokens": 2000}],
        },
    )
    assert conflict.status_code == 409
    assert await db.scalar(select(func.count()).select_from(EventCost)) == 1
    success = await client.post(
        "/api/v1/ingest/events/batch",
        headers=headers,
        json={
            "events": [
                payload,
                normalized_event("new"),
                normalized_event("unpriced", model="missing"),
            ],
        },
    )
    assert success.status_code == 200
    assert success.json()["data"]["created_count"] == 2
    assert await db.scalar(select(func.count()).select_from(EventCost)) == 3


async def test_explicit_recalculation_preserves_history_until_replacement_requested(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    project_id, key = await setup_project(client)
    payload = normalized_event()
    first = await ingest(client, key, payload)
    event_id = first.json()["data"]["event"]["id"]
    detail_url = f"/api/v1/projects/{project_id}/events/{event_id}"
    recalc_url = f"/api/v1/projects/{project_id}/events/recalculate"
    original = (await client.get(detail_url)).json()["data"]["event"]["cost"]
    assert original["total_cost"] is None
    price_payload = price_input()
    old_price = (await import_prices(db, [price_payload]))[0]
    assert (await ingest(client, key, payload)).status_code == 200
    assert (await client.get(detail_url)).json()["data"]["event"]["cost"] == original
    recalculated = await client.post(recalc_url, headers=ORIGIN, json={"event_ids": [event_id]})
    assert recalculated.status_code == 200
    assert recalculated.json()["data"]["updated_count"] == 1
    snapshot = recalculated.json()["data"]["costs"][0]
    assert snapshot["total_cost"] == "0.003900000000000000"
    await retire_price(db, old_price.id)
    replacement = price_input(
        effective_from=price_payload.effective_from,
        input_price_per_million="10",
        catalog_version="correction-v2",
    )
    new_price = (await import_prices(db, [replacement]))[0]
    default_retry = await client.post(recalc_url, headers=ORIGIN, json={"event_ids": [event_id]})
    assert default_retry.json()["data"]["skipped_count"] == 1
    assert default_retry.json()["data"]["costs"][0]["total_cost"] == snapshot["total_cost"]
    replaced = await client.post(
        recalc_url,
        headers=ORIGIN,
        json={
            "event_ids": [event_id],
            "replace_calculated": True,
        },
    )
    assert replaced.json()["data"]["costs"][0]["model_price_id"] == str(new_price.id)
    assert replaced.json()["data"]["costs"][0]["total_cost"] == "0.010300000000000000"
    assert replaced.json()["data"]["costs"][0]["id"] == snapshot["id"]
    assert await db.scalar(select(func.count()).select_from(EventCost)) == 1


async def test_recalculation_authorization_origin_and_cross_project_scope(
    client: AsyncClient,
    db: AsyncSession,
    app: Any,
) -> None:
    org_id = await register(client)
    project = await create_project(client, org_id)
    key = (await create_key(client, project["id"]))["raw_key"]
    first = await ingest(client, key, normalized_event())
    event_id = first.json()["data"]["event"]["id"]
    url = f"/api/v1/projects/{project['id']}/events/recalculate"
    body = {"event_ids": [event_id]}
    assert (await client.post(url, json=body)).status_code == 403
    other_project = await create_project(client, org_id, "Second Project")
    assert (
        await client.post(
            f"/api/v1/projects/{other_project['id']}/events/recalculate", headers=ORIGIN, json=body
        )
    ).status_code == 404
    await add_member(db, org_id)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as member:
        await login_member(member)
        assert (await member.post(url, headers=ORIGIN, json=body)).status_code == 403
        detail = await member.get(f"/api/v1/projects/{project['id']}/events/{event_id}")
        assert detail.status_code == 200
        assert detail.json()["data"]["event"]["cost"]["status"] == "unpriced"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as outsider:
        await register(outsider, "outside@example.com", "Outside")
        assert (await outsider.post(url, headers=ORIGIN, json=body)).status_code == 404
        assert (
            await outsider.get(f"/api/v1/projects/{project['id']}/events/{event_id}")
        ).status_code == 404


async def test_database_rejects_fake_zero_unpriced_cost(
    client: AsyncClient, db: AsyncSession
) -> None:
    _, key = await setup_project(client)
    await ingest(client, key, normalized_event())
    cost = await db.scalar(select(EventCost))
    assert cost is not None
    cost.total_cost = Decimal("0")
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


async def test_smallest_rate_is_preserved_by_database_and_json(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await import_prices(db, [price_input(input_price_per_million="0.000000000001")])
    project_id, key = await setup_project(client)
    response = await ingest(
        client,
        key,
        normalized_event(
            input_tokens=1,
            cached_input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
        ),
    )
    event_id = response.json()["data"]["event"]["id"]
    detail = await client.get(f"/api/v1/projects/{project_id}/events/{event_id}")
    assert detail.json()["data"]["event"]["cost"]["total_cost"] == "0.000000000000000001"
    stored = await db.scalar(select(EventCost))
    assert stored is not None
    assert stored.total_cost == Decimal("0.000000000000000001")
    stored.uncached_input_cost = Decimal("NaN")
    stored.total_cost = Decimal("NaN")
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


async def test_concurrent_recalculation_serializes_and_skips_saved_result(
    client: AsyncClient,
    db: AsyncSession,
    app: Any,
) -> None:
    project_id, key = await setup_project(client)
    response = await ingest(client, key, normalized_event())
    event_id = response.json()["data"]["event"]["id"]
    await import_prices(db, [price_input()])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other:
        other.cookies.update(client.cookies)
        url = f"/api/v1/projects/{project_id}/events/recalculate"
        results = await asyncio.gather(
            client.post(url, headers=ORIGIN, json={"event_ids": [event_id]}),
            other.post(url, headers=ORIGIN, json={"event_ids": [event_id]}),
        )
    assert [result.status_code for result in results] == [200, 200]
    assert sorted(result.json()["data"]["updated_count"] for result in results) == [0, 1]
    assert await db.scalar(select(func.count()).select_from(EventCost)) == 1


async def test_cost_failure_rolls_back_usage_and_cost_together(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import usage_events

    await import_prices(db, [price_input()])
    _, key = await setup_project(client)

    async def fail_after_insert(
        session: AsyncSession, events: list[UsageEvent], currency: str
    ) -> None:
        await create_event_costs(session, events, currency)
        raise RuntimeError("Simulated transaction failure")

    monkeypatch.setattr(usage_events, "create_event_costs", fail_after_insert)
    with pytest.raises(RuntimeError, match="Simulated transaction failure"):
        await ingest(client, key, normalized_event())
    assert await db.scalar(select(func.count()).select_from(UsageEvent)) == 0
    assert await db.scalar(select(func.count()).select_from(EventCost)) == 0
