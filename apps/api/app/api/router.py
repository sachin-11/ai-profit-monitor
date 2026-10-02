import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_database_session
from app.schemas.status import HealthData, ReadyData, StatusResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health", response_model=StatusResponse[HealthData])
async def health() -> StatusResponse[HealthData]:
    return StatusResponse(data=HealthData(status="healthy"))


@router.get(
    "/ready",
    response_model=StatusResponse[ReadyData],
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": StatusResponse[ReadyData]}},
)
async def ready(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> StatusResponse[ReadyData] | JSONResponse:
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Database readiness check failed")
        payload: StatusResponse[ReadyData] = StatusResponse(
            success=False,
            data=ReadyData(status="not_ready", database="unavailable"),
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=payload.model_dump(),
        )
    return StatusResponse(data=ReadyData(status="ready", database="available"))
