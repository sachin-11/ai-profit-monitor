from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.errors import ApiError
from app.models.event_cost import CostStatus, EventCost
from app.models.model_price import ModelPrice, ReasoningBillingMode
from app.models.usage_event import UsageEvent

CALCULATION_VERSION = "text_tokens_v1"
MILLION = Decimal("1000000")
TEXT_OPERATIONS = {"chat", "completion", "completions", "text", "text_generation", "generate_text"}
UNSUPPORTED_TAGS = {
    "cache_write_tokens",
    "cache_creation_input_tokens",
    "image_tokens",
    "audio_tokens",
    "video_tokens",
    "tool_calls",
    "tool_call_fees",
    "web_search",
    "storage",
    "fine_tuning",
    "batch",
    "batch_discount",
    "service_tier",
    "pricing_tier",
    "region",
    "enterprise_pricing",
    "committed_use",
    "unsupported_pricing_dimensions",
}


def calculate_cost(event: UsageEvent, price: ModelPrice | None, currency: str) -> dict[str, Any]:
    """Pure Decimal calculation. Missing/unsupported rates never produce a numeric total."""
    result: dict[str, Any] = {
        "usage_event_id": event.id,
        "model_price_id": price.id if price is not None else None,
        "status": CostStatus.UNPRICED,
        "currency": currency,
        "uncached_input_tokens": max(0, event.input_tokens - event.cached_input_tokens),
        "cached_input_tokens": max(0, event.cached_input_tokens),
        "regular_output_tokens": max(0, event.output_tokens - event.reasoning_tokens),
        "reasoning_tokens": max(0, event.reasoning_tokens),
        "uncached_input_cost": None,
        "cached_input_cost": None,
        "output_cost": None,
        "reasoning_cost": None,
        "total_cost": None,
        "calculation_version": CALCULATION_VERSION,
        "calculated_at": datetime.now(UTC),
        "reason_code": None,
        "reason_detail": None,
    }

    def unavailable(status: CostStatus, code: str, detail: str) -> dict[str, Any]:
        result.update(status=status, reason_code=code, reason_detail=detail)
        return result

    if event.schema_version == 1 and (event.cached_input_tokens or event.reasoning_tokens):
        # v1 explicitly documented independent counters. Never reinterpret historical metadata.
        result.update(
            uncached_input_tokens=0,
            cached_input_tokens=0,
            regular_output_tokens=0,
            reasoning_tokens=0,
        )
        return unavailable(
            CostStatus.UNSUPPORTED,
            "legacy_token_semantics",
            "Schema v1 cached/reasoning token semantics are ambiguous; use normalized schema v2",
        )
    if (
        min(
            event.input_tokens,
            event.cached_input_tokens,
            event.output_tokens,
            event.reasoning_tokens,
        )
        < 0
        or event.cached_input_tokens > event.input_tokens
        or event.reasoning_tokens > event.output_tokens
    ):
        return unavailable(
            CostStatus.INVALID, "invalid_token_subsets", "Token subsets are inconsistent"
        )
    if event.schema_version not in {1, 2}:
        return unavailable(
            CostStatus.UNSUPPORTED, "unsupported_schema_version", "Event schema is not supported"
        )
    if event.operation is not None and event.operation.strip().lower() not in TEXT_OPERATIONS:
        return unavailable(
            CostStatus.UNSUPPORTED,
            "unsupported_operation",
            "Only standard text-token operations are priced",
        )
    for key, value in event.tags.items():
        normalized_key = key.strip().lower()
        if normalized_key in UNSUPPORTED_TAGS or (
            normalized_key in {"modality", "input_modality", "output_modality"}
            and value.strip().lower() != "text"
        ):
            return unavailable(
                CostStatus.UNSUPPORTED,
                "unsupported_pricing_dimension",
                "Event declares a pricing dimension outside standard text-token pricing",
            )
    if price is None:
        return unavailable(
            CostStatus.UNPRICED,
            "price_not_found",
            "No effective price for the exact provider, model, and currency",
        )
    if event.cached_input_tokens and price.cached_input_price_per_million is None:
        return unavailable(
            CostStatus.UNPRICED, "cached_input_rate_missing", "Cached input rate is not specified"
        )
    if (
        event.reasoning_tokens
        and price.reasoning_billing_mode == ReasoningBillingMode.NOT_SUPPORTED
    ):
        return unavailable(
            CostStatus.UNSUPPORTED,
            "reasoning_not_supported",
            "This price does not support reasoning tokens",
        )

    reasoning_rate = price.output_price_per_million
    if price.reasoning_billing_mode == ReasoningBillingMode.SEPARATELY_PRICED:
        if price.reasoning_price_per_million is None:
            return unavailable(
                CostStatus.UNPRICED,
                "reasoning_rate_missing",
                "Separate reasoning rate is not specified",
            )
        reasoning_rate = price.reasoning_price_per_million
    # Rate scale <=12, count <=1e9, division by 1e6: NUMERIC(38,18) stores every digit.
    # A private context prevents unrelated Decimal context changes from rounding our results.
    with localcontext() as context:
        context.prec = 60
        uncached = (
            Decimal(result["uncached_input_tokens"]) * price.input_price_per_million / MILLION
        )
        cached = (
            Decimal(event.cached_input_tokens)
            * (price.cached_input_price_per_million or Decimal("0"))
            / MILLION
        )
        output = Decimal(result["regular_output_tokens"]) * price.output_price_per_million / MILLION
        reasoning = Decimal(event.reasoning_tokens) * reasoning_rate / MILLION
        result.update(
            status=CostStatus.CALCULATED,
            uncached_input_cost=uncached,
            cached_input_cost=cached,
            output_cost=output,
            reasoning_cost=reasoning,
            total_cost=uncached + cached + output + reasoning,
        )
    return result


async def effective_prices(
    db: AsyncSession,
    events: list[UsageEvent],
    currency: str,
) -> dict[uuid.UUID, ModelPrice]:
    rows = await db.execute(
        select(UsageEvent.id, ModelPrice)
        .join(
            ModelPrice,
            and_(
                ModelPrice.provider == func.lower(UsageEvent.provider),
                ModelPrice.model == func.lower(UsageEvent.model),
                ModelPrice.currency == currency,
                ModelPrice.is_active.is_(True),
                ModelPrice.effective_from <= UsageEvent.occurred_at,
                or_(
                    ModelPrice.effective_to.is_(None),
                    ModelPrice.effective_to > UsageEvent.occurred_at,
                ),
            ),
        )
        .where(UsageEvent.id.in_([event.id for event in events]))
    )
    return {event_id: price for event_id, price in rows}


async def create_event_costs(db: AsyncSession, events: list[UsageEvent], currency: str) -> None:
    if not events:
        return
    prices = await effective_prices(db, events, currency)
    values = [calculate_cost(event, prices.get(event.id), currency) for event in events]
    # The caller owns the transaction; event insertion and costs commit/rollback together.
    await db.execute(
        insert(EventCost)
        .values(values)
        .on_conflict_do_nothing(index_elements=[EventCost.usage_event_id])
    )


async def recalculate_costs(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    event_ids: list[uuid.UUID],
    currency: str,
    replace_calculated: bool,
) -> tuple[list[EventCost], int]:
    try:
        # All writers lock events in UUID order, preventing concurrent recalculation races.
        events = list(
            (
                await db.scalars(
                    select(UsageEvent)
                    .where(
                        UsageEvent.project_id == project_id,
                        UsageEvent.id.in_(event_ids),
                    )
                    .order_by(UsageEvent.id)
                    .with_for_update()
                )
            ).all()
        )
        if len(events) != len(event_ids):
            raise ApiError(404, "not_found", "One or more events were not found in this project")
        existing = {
            cost.usage_event_id: cost
            for cost in (
                await db.scalars(
                    select(EventCost).where(EventCost.usage_event_id.in_(event_ids)),
                )
            ).all()
        }
        prices = await effective_prices(db, events, currency)
        updated_count = 0
        for event in events:
            cost = existing.get(event.id)
            if cost is not None and cost.status == CostStatus.CALCULATED and not replace_calculated:
                continue
            # Existing snapshots retain their selected currency even if deployment defaults change.
            selected_currency = cost.currency if cost is not None and cost.currency else currency
            if selected_currency != currency:
                selected = await effective_prices(db, [event], selected_currency)
                price = selected.get(event.id)
            else:
                price = prices.get(event.id)
            values = calculate_cost(event, price, selected_currency)
            if cost is None:
                db.add(EventCost(**values))
            else:
                for field, value in values.items():
                    setattr(cost, field, value)
            updated_count += 1
        await db.commit()
        rows = list(
            (
                await db.scalars(
                    select(EventCost)
                    .options(joinedload(EventCost.model_price))
                    .where(EventCost.usage_event_id.in_(event_ids))
                    .order_by(EventCost.usage_event_id)
                    .execution_options(populate_existing=True)
                )
            ).all()
        )
        return rows, updated_count
    except Exception:
        await db.rollback()
        raise
