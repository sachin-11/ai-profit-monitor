from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import DatabaseSession, enforce_trusted_origin, get_request_settings
from app.api.project_dependencies import ProjectAdmin, ProjectMember
from app.models.usage_event import EventStatus
from app.schemas.common import ApiResponse, ErrorResponse
from app.schemas.pricing import RecalculateCosts, RecalculateData
from app.schemas.usage_event import EventData, EventListData
from app.services.costs import recalculate_costs
from app.services.usage_events import get_event, query_events

router = APIRouter(prefix="/projects/{project_id}/events", tags=["usage events"])


@router.post(
    "/recalculate",
    response_model=ApiResponse[RecalculateData],
    dependencies=[Depends(enforce_trusted_origin)],
    summary="Explicitly recalculate up to 100 project events; preserve calculated costs by default",
)
async def recalculate(
    project_id: uuid.UUID,
    payload: RecalculateCosts,
    request: Request,
    context: ProjectAdmin,
    db: DatabaseSession,
) -> ApiResponse[RecalculateData]:
    costs, updated = await recalculate_costs(
        db,
        project_id=context.project.id,
        event_ids=payload.event_ids,
        currency=get_request_settings(request).cost_currency,
        replace_calculated=payload.replace_calculated,
    )
    return ApiResponse(
        data=RecalculateData(
            costs=costs,
            updated_count=updated,
            skipped_count=len(costs) - updated,
        )
    )


@router.get(
    "",
    response_model=ApiResponse[EventListData],
    summary="List recent project events with cursor pagination",
)
async def events(
    project_id: uuid.UUID,
    request: Request,
    context: ProjectMember,
    db: DatabaseSession,
    limit: int | None = Query(default=None, ge=1, le=500),
    cursor: str | None = Query(default=None, max_length=256),
    provider: str | None = Query(default=None, max_length=40),
    model: str | None = Query(default=None, max_length=120),
    feature: str | None = Query(default=None, max_length=100),
    customer_external_id: str | None = Query(default=None, max_length=128),
    status: EventStatus | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> ApiResponse[EventListData]:
    rows, next_cursor = await query_events(
        db,
        project_id=context.project.id,
        settings=get_request_settings(request),
        limit=limit,
        cursor=cursor,
        provider=provider,
        model=model,
        feature=feature,
        customer_external_id=customer_external_id,
        status=status,
        start_time=start_time,
        end_time=end_time,
    )
    return ApiResponse(data=EventListData(events=rows, next_cursor=next_cursor))


@router.get(
    "/{event_id}",
    response_model=ApiResponse[EventData],
    responses={404: {"model": ErrorResponse}},
    summary="Get one event within an accessible project",
)
async def event_detail(
    project_id: uuid.UUID,
    event_id: uuid.UUID,
    context: ProjectMember,
    db: DatabaseSession,
) -> ApiResponse[EventData]:
    event = await get_event(db, project_id=context.project.id, event_id=event_id)
    return ApiResponse(data=EventData(event=event))
