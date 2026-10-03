from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.models.model_price import ModelPrice
from app.schemas.pricing import ModelPriceCreate


async def import_prices(
    db: AsyncSession,
    prices: list[ModelPriceCreate],
    *,
    close_previous: bool = False,
) -> list[ModelPrice]:
    """Operator-only import. Rates are immutable; an explicit rollover can shorten intervals."""
    try:
        # Serialize operator imports/retirement. The exclusion constraint also protects raw SQL.
        await db.execute(text("SELECT pg_advisory_xact_lock(714204001)"))
        rows = []
        for price in sorted(
            prices, key=lambda p: (p.provider, p.model, p.currency, p.effective_from)
        ):
            if close_previous and price.is_active:
                previous = await db.scalar(
                    select(ModelPrice)
                    .where(
                        ModelPrice.provider == price.provider,
                        ModelPrice.model == price.model,
                        ModelPrice.currency == price.currency,
                        ModelPrice.is_active.is_(True),
                        ModelPrice.effective_from < price.effective_from,
                        or_(
                            ModelPrice.effective_to.is_(None),
                            ModelPrice.effective_to > price.effective_from,
                        ),
                    )
                    .with_for_update()
                )
                if previous is not None:
                    previous.effective_to = price.effective_from
                    await db.flush()
            row = ModelPrice(**price.model_dump())
            db.add(row)
            await db.flush()
            rows.append(row)
        await db.commit()
        return rows
    except IntegrityError as exc:
        await db.rollback()
        raise ApiError(
            409,
            "pricing_conflict",
            "Pricing overlaps an active version or violates catalog constraints",
        ) from exc
    except Exception:
        await db.rollback()
        raise


async def retire_price(db: AsyncSession, price_id: uuid.UUID) -> None:
    await db.execute(text("SELECT pg_advisory_xact_lock(714204001)"))
    row = await db.scalar(select(ModelPrice).where(ModelPrice.id == price_id).with_for_update())
    if row is None:
        raise ApiError(404, "not_found", "Pricing record not found")
    row.is_active = False
    await db.commit()


async def list_prices(
    db: AsyncSession,
    *,
    provider: str | None,
    model: str | None,
    currency: str,
    at: datetime | None,
    limit: int,
    offset: int,
) -> list[ModelPrice]:
    statement = select(ModelPrice).where(ModelPrice.currency == currency)
    if provider is not None:
        statement = statement.where(ModelPrice.provider == provider.strip().lower())
    if model is not None:
        statement = statement.where(ModelPrice.model == model.strip().lower())
    if at is not None:
        statement = statement.where(
            ModelPrice.is_active.is_(True),
            ModelPrice.effective_from <= at,
            or_(ModelPrice.effective_to.is_(None), ModelPrice.effective_to > at),
        )
    return list(
        (
            await db.scalars(
                statement.order_by(
                    ModelPrice.provider,
                    ModelPrice.model,
                    ModelPrice.effective_from.desc(),
                    ModelPrice.id,
                )
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
