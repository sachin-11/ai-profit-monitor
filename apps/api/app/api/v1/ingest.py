from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.api.dependencies import DatabaseSession, get_request_settings
from app.api.project_dependencies import IngestionProject
from app.core.errors import ApiError
from app.schemas.common import ApiResponse, ErrorResponse
from app.schemas.usage_event import (
    BatchIngestData,
    IngestData,
    UsageEventBatch,
    UsageEventCreate,
)
from app.services.usage_events import ingest_events

router = APIRouter(prefix="/ingest/events", tags=["usage ingestion"])


@router.post(
    "",
    response_model=ApiResponse[IngestData],
    status_code=status.HTTP_201_CREATED,
    responses={401: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    summary="Ingest one normalized usage event with a project API key",
)
async def ingest_single(
    payload: UsageEventCreate,
    request: Request,
    response: Response,
    context: IngestionProject,
    db: DatabaseSession,
) -> ApiResponse[IngestData]:
    result = (
        await ingest_events(
            db,
            project=context.project,
            events=[payload],
            settings=get_request_settings(request),
        )
    )[0]
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return ApiResponse(data=IngestData(event=result))


@router.post(
    "/batch",
    response_model=ApiResponse[BatchIngestData],
    responses={401: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    summary="Atomically ingest a batch of normalized usage events",
)
async def ingest_batch(
    payload: UsageEventBatch,
    request: Request,
    context: IngestionProject,
    db: DatabaseSession,
) -> ApiResponse[BatchIngestData]:
    settings = get_request_settings(request)
    if len(payload.events) > settings.ingestion_max_batch_size:
        raise ApiError(413, "batch_too_large", "Event batch exceeds the configured maximum")
    results = await ingest_events(
        db, project=context.project, events=payload.events, settings=settings
    )
    created_count = sum(result.created for result in results)
    return ApiResponse(
        data=BatchIngestData(
            created_count=created_count,
            existing_count=len(results) - created_count,
            results=results,
        )
    )
