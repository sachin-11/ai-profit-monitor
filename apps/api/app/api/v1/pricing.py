from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query, Request

from app.api.dependencies import CurrentAuth, DatabaseSession, get_request_settings
from app.core.errors import ApiError
from app.schemas.common import ApiResponse
from app.schemas.pricing import PriceListData
from app.services.pricing import list_prices

router = APIRouter(prefix="/pricing/models", tags=["model pricing"])


@router.get("", response_model=ApiResponse[PriceListData])
async def model_prices(
    request: Request,
    auth: CurrentAuth,
    db: DatabaseSession,
    provider: str | None = Query(default=None, min_length=2, max_length=40),
    model: str | None = Query(default=None, min_length=1, max_length=120),
    currency: str | None = Query(default=None, pattern=r"^[A-Z]{3}$"),
    at: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
) -> ApiResponse[PriceListData]:
    if at is not None and at.tzinfo is None:
        raise ApiError(422, "invalid_timestamp", "Pricing timestamp must be timezone aware")
    rows = await list_prices(
        db,
        provider=provider,
        model=model,
        currency=currency or get_request_settings(request).cost_currency,
        at=at,
        limit=limit,
        offset=offset,
    )
    return ApiResponse(data=PriceListData(prices=rows))
