"""Run from apps/api: uv run python -m app.cli.pricing --help."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from decimal import Decimal
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.session import dispose_database, session_factory
from app.schemas.pricing import ModelPriceCreate
from app.services.costs import recalculate_costs
from app.services.pricing import import_prices, retire_price


def read_catalog(path: Path) -> list[ModelPriceCreate]:
    if path.stat().st_size > 1_048_576:
        raise ValueError("Pricing file must not exceed 1 MiB")
    data = json.loads(path.read_text(encoding="utf-8-sig"), parse_float=Decimal)
    if not isinstance(data, list) or not 1 <= len(data) <= 100:
        raise ValueError("Pricing file must contain an array of 1 to 100 records")
    return TypeAdapter(list[ModelPriceCreate]).validate_python(data)


async def run(args: argparse.Namespace) -> None:
    try:
        async with session_factory() as db:
            if args.command == "import":
                prices = read_catalog(Path(args.file))
                rows = await import_prices(db, prices, close_previous=args.close_previous)
                print(
                    json.dumps({"imported": len(rows), "price_ids": [str(row.id) for row in rows]})
                )
            elif args.command == "retire":
                await retire_price(db, args.price_id)
                print("Pricing version retired; existing event costs preserved")
            elif args.command == "recalculate":
                ids = list(dict.fromkeys(args.event_id))
                if len(ids) > 100:
                    raise ValueError("Recalculate at most 100 explicit event IDs per invocation")
                costs, updated = await recalculate_costs(
                    db,
                    project_id=args.project_id,
                    event_ids=ids,
                    currency=get_settings().cost_currency,
                    replace_calculated=args.replace_calculated,
                )
                print(json.dumps({"updated": updated, "skipped": len(costs) - updated}))
    finally:
        await dispose_database()


def main() -> None:
    parser = argparse.ArgumentParser(description="Operator-only model price catalog and cost tools")
    commands = parser.add_subparsers(dest="command", required=True)
    importer = commands.add_parser(
        "import", help="Import exact verified rates; no provider network calls"
    )
    importer.add_argument("file")
    importer.add_argument(
        "--close-previous",
        action="store_true",
        help="Explicitly end a prior active interval at the new start",
    )
    retire = commands.add_parser("retire", help="Retire a version without changing existing costs")
    retire.add_argument("price_id", type=uuid.UUID)
    recalculate = commands.add_parser(
        "recalculate", help="Explicitly re-evaluate events within one project"
    )
    recalculate.add_argument("--project-id", type=uuid.UUID, required=True)
    recalculate.add_argument("--event-id", type=uuid.UUID, action="append", required=True)
    recalculate.add_argument(
        "--replace-calculated",
        action="store_true",
        help="Explicitly replace previously calculated snapshots",
    )
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except ApiError as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        raise SystemExit(1) from None
    except (ValueError, ValidationError, OSError) as exc:
        print(
            f"Invalid pricing input ({type(exc).__name__}); check file fields and limits",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
