from __future__ import annotations

import base64
import binascii
import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ApiError
from app.models.project import Project
from app.models.usage_event import EventStatus, UsageEvent
from app.schemas.usage_event import IngestResult, UsageEventCreate


def event_fingerprint(event: UsageEventCreate) -> str:
    canonical = json.dumps(
        event.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_event_time(event: UsageEventCreate, settings: Settings, now: datetime) -> None:
    if event.occurred_at > now + timedelta(seconds=settings.event_max_future_seconds):
        raise ApiError(422, "invalid_event", "Event occurred_at is too far in the future")
    if event.occurred_at < now - timedelta(days=settings.event_max_age_days):
        raise ApiError(422, "invalid_event", "Event occurred_at is too old")


async def ingest_events(
    db: AsyncSession,
    *,
    project: Project,
    events: list[UsageEventCreate],
    settings: Settings,
) -> list[IngestResult]:
    now = datetime.now(UTC)
    unique: dict[str, tuple[UsageEventCreate, str]] = {}
    for event in events:
        validate_event_time(event, settings, now)
        fingerprint = event_fingerprint(event)
        previous = unique.get(event.client_event_id)
        if previous is not None and previous[1] != fingerprint:
            raise ApiError(409, "duplicate_event_conflict", "Event ID has a different payload")
        unique[event.client_event_id] = (event, fingerprint)

    values: list[dict[str, Any]] = []
    for event, fingerprint in unique.values():
        values.append(
            {
                **event.model_dump(mode="python"),
                "id": uuid.uuid4(),
                "organization_id": project.organization_id,
                "project_id": project.id,
                "payload_fingerprint": fingerprint,
                "received_at": now,
                "created_at": now,
            }
        )

    try:
        inserted_rows = await db.execute(
            insert(UsageEvent)
            .values(values)
            .on_conflict_do_nothing(constraint="uq_usage_events_project_client_id")
            .returning(UsageEvent.client_event_id)
        )
        created_ids = set(inserted_rows.scalars().all())
        stored_rows = await db.scalars(
            select(UsageEvent).where(
                UsageEvent.project_id == project.id,
                UsageEvent.client_event_id.in_(unique),
            )
        )
        stored = {row.client_event_id: row for row in stored_rows}
        for client_event_id, (_, fingerprint) in unique.items():
            if stored[client_event_id].payload_fingerprint != fingerprint:
                raise ApiError(409, "duplicate_event_conflict", "Event ID has a different payload")
        seen_ids: set[str] = set()
        results = []
        for event in events:
            results.append(
                IngestResult(
                    id=stored[event.client_event_id].id,
                    client_event_id=event.client_event_id,
                    created=event.client_event_id in created_ids
                    and event.client_event_id not in seen_ids,
                )
            )
            seen_ids.add(event.client_event_id)
        await db.commit()
        return results
    except Exception:
        await db.rollback()
        raise


def encode_cursor(event: UsageEvent) -> str:
    payload = json.dumps([event.occurred_at.isoformat(), str(event.id)], separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    if len(cursor) > 256:
        raise ApiError(422, "invalid_cursor", "Invalid event cursor")
    try:
        decoded = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode("utf-8")
        timestamp_value, id_value = json.loads(decoded)
        occurred_at = datetime.fromisoformat(timestamp_value)
        if occurred_at.tzinfo is None:
            raise ValueError("cursor timestamp must be timezone aware")
        return occurred_at.astimezone(UTC), uuid.UUID(id_value)
    except (ValueError, TypeError, UnicodeDecodeError, binascii.Error) as exc:
        raise ApiError(422, "invalid_cursor", "Invalid event cursor") from exc


async def query_events(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    settings: Settings,
    limit: int | None,
    cursor: str | None,
    provider: str | None,
    model: str | None,
    feature: str | None,
    customer_external_id: str | None,
    status: EventStatus | None,
    start_time: datetime | None,
    end_time: datetime | None,
) -> tuple[list[UsageEvent], str | None]:
    page_size = limit or settings.event_page_size
    if page_size > settings.event_max_page_size:
        raise ApiError(422, "invalid_page_size", "Event page size exceeds the configured maximum")
    now = datetime.now(UTC)
    start = start_time or now - timedelta(days=30)
    end = end_time or now + timedelta(seconds=settings.event_max_future_seconds)
    if start.tzinfo is None or end.tzinfo is None or start > end:
        raise ApiError(422, "invalid_date_range", "A valid timezone-aware date range is required")
    if end - start > timedelta(days=settings.event_max_query_days):
        raise ApiError(422, "invalid_date_range", "Event date range exceeds the configured maximum")

    statement: Select[tuple[UsageEvent]] = select(UsageEvent).where(
        UsageEvent.project_id == project_id,
        UsageEvent.occurred_at >= start,
        UsageEvent.occurred_at <= end,
    )
    if provider is not None:
        statement = statement.where(UsageEvent.provider == provider)
    if model is not None:
        statement = statement.where(UsageEvent.model == model)
    if feature is not None:
        statement = statement.where(UsageEvent.feature == feature)
    if customer_external_id is not None:
        statement = statement.where(UsageEvent.customer_external_id == customer_external_id)
    if status is not None:
        statement = statement.where(UsageEvent.status == status)
    if cursor is not None:
        cursor_time, cursor_id = decode_cursor(cursor)
        statement = statement.where(
            tuple_(UsageEvent.occurred_at, UsageEvent.id) < (cursor_time, cursor_id)
        )
    result = await db.scalars(
        statement.order_by(UsageEvent.occurred_at.desc(), UsageEvent.id.desc()).limit(page_size + 1)
    )
    rows = list(result.all())
    has_more = len(rows) > page_size
    page = rows[:page_size]
    return page, encode_cursor(page[-1]) if has_more else None


async def get_event(db: AsyncSession, *, project_id: uuid.UUID, event_id: uuid.UUID) -> UsageEvent:
    event = await db.scalar(
        select(UsageEvent).where(UsageEvent.id == event_id, UsageEvent.project_id == project_id)
    )
    if event is None:
        raise ApiError(404, "not_found", "Event not found")
    return event
