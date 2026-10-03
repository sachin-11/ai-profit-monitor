"""Versioned text-token prices and auditable event costs.

Revision ID: 20261003_0004
Revises: 20261003_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261003_0004"
down_revision: str | None = "20261003_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

reasoning_mode = postgresql.ENUM(
    "included_in_output",
    "separately_priced",
    "not_supported",
    name="reasoning_billing_mode",
    create_type=False,
)
cost_status = postgresql.ENUM(
    "calculated",
    "unpriced",
    "unsupported",
    "invalid",
    name="event_cost_status",
    create_type=False,
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    reasoning_mode.create(op.get_bind(), checkfirst=True)
    cost_status.create(op.get_bind(), checkfirst=True)
    op.drop_constraint("ck_usage_events_schema_version", "usage_events", type_="check")
    op.create_check_constraint(
        "ck_usage_events_schema_version", "usage_events", "schema_version IN (1, 2)"
    )
    op.create_check_constraint(
        "ck_usage_events_token_subsets",
        "usage_events",
        "schema_version <> 2 OR (cached_input_tokens <= input_tokens "
        "AND reasoning_tokens <= output_tokens)",
    )
    op.create_table(
        "model_prices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("input_price_per_million", sa.Numeric(24, 12), nullable=False),
        sa.Column("cached_input_price_per_million", sa.Numeric(24, 12), nullable=True),
        sa.Column("output_price_per_million", sa.Numeric(24, 12), nullable=False),
        sa.Column("reasoning_price_per_million", sa.Numeric(24, 12), nullable=True),
        sa.Column("reasoning_billing_mode", reasoning_mode, nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_name", sa.String(200), nullable=False),
        sa.Column("source_url", sa.String(2048), nullable=True),
        sa.Column("source_retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("catalog_version", sa.String(100), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_model_prices"),
        sa.CheckConstraint(
            "provider = lower(btrim(provider)) AND provider ~ '^[a-z][a-z0-9_]+$' "
            "AND model = lower(btrim(model)) AND length(model) > 0",
            name="ck_model_prices_normalized_names",
        ),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_model_prices_currency"),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from", name="ck_model_prices_interval"
        ),
        sa.CheckConstraint(
            "input_price_per_million BETWEEN 0 AND 1000000000 "
            "AND output_price_per_million BETWEEN 0 AND 1000000000 "
            "AND (cached_input_price_per_million IS NULL OR "
            "cached_input_price_per_million BETWEEN 0 AND 1000000000) "
            "AND (reasoning_price_per_million IS NULL OR "
            "reasoning_price_per_million BETWEEN 0 AND 1000000000)",
            name="ck_model_prices_rates",
        ),
        sa.CheckConstraint(
            "(reasoning_billing_mode = 'separately_priced' "
            "AND reasoning_price_per_million IS NOT NULL) "
            "OR (reasoning_billing_mode <> 'separately_priced' "
            "AND reasoning_price_per_million IS NULL)",
            name="ck_model_prices_reasoning_rate",
        ),
    )
    op.execute("""
        ALTER TABLE model_prices ADD CONSTRAINT ex_model_prices_active_interval
        EXCLUDE USING gist (provider WITH =, model WITH =, currency WITH =,
            tstzrange(effective_from, effective_to, '[)') WITH &&) WHERE (is_active)
    """)
    op.create_index(
        "ix_model_prices_lookup",
        "model_prices",
        ["provider", "model", "currency", "effective_from"],
    )
    op.execute("""
        CREATE FUNCTION protect_model_price_history() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF (to_jsonb(NEW) - 'effective_to' - 'is_active') IS DISTINCT FROM
               (to_jsonb(OLD) - 'effective_to' - 'is_active')
               OR (OLD.effective_to IS NOT NULL AND
                   (NEW.effective_to IS NULL OR NEW.effective_to > OLD.effective_to))
               OR (NOT OLD.is_active AND NEW.is_active) THEN
                RAISE EXCEPTION 'Pricing history is immutable; insert a new version'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$
    """)
    op.execute("""
        CREATE TRIGGER model_prices_preserve_history BEFORE UPDATE ON model_prices
        FOR EACH ROW EXECUTE FUNCTION protect_model_price_history()
    """)
    op.create_table(
        "event_costs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("usage_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_price_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", cost_status, nullable=False),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("uncached_input_tokens", sa.BigInteger(), nullable=False),
        sa.Column("cached_input_tokens", sa.BigInteger(), nullable=False),
        sa.Column("regular_output_tokens", sa.BigInteger(), nullable=False),
        sa.Column("reasoning_tokens", sa.BigInteger(), nullable=False),
        sa.Column("uncached_input_cost", sa.Numeric(38, 18), nullable=True),
        sa.Column("cached_input_cost", sa.Numeric(38, 18), nullable=True),
        sa.Column("output_cost", sa.Numeric(38, 18), nullable=True),
        sa.Column("reasoning_cost", sa.Numeric(38, 18), nullable=True),
        sa.Column("total_cost", sa.Numeric(38, 18), nullable=True),
        sa.Column("calculation_version", sa.String(40), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason_code", sa.String(80), nullable=True),
        sa.Column("reason_detail", sa.String(300), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_event_costs"),
        sa.UniqueConstraint("usage_event_id", name="uq_event_costs_usage_event_id"),
        sa.ForeignKeyConstraint(["usage_event_id"], ["usage_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_price_id"], ["model_prices.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "uncached_input_tokens >= 0 AND cached_input_tokens >= 0 "
            "AND regular_output_tokens >= 0 AND reasoning_tokens >= 0",
            name="ck_event_costs_counts",
        ),
        sa.CheckConstraint(
            "currency IS NULL OR currency ~ '^[A-Z]{3}$'", name="ck_event_costs_currency"
        ),
        sa.CheckConstraint(
            "(status = 'calculated' AND model_price_id IS NOT NULL AND currency IS NOT NULL "
            "AND reason_code IS NULL AND reason_detail IS NULL "
            "AND uncached_input_cost IS NOT NULL AND uncached_input_cost >= 0 "
            "AND cached_input_cost IS NOT NULL AND cached_input_cost >= 0 "
            "AND output_cost IS NOT NULL AND output_cost >= 0 "
            "AND reasoning_cost IS NOT NULL AND reasoning_cost >= 0 "
            "AND total_cost IS NOT NULL AND total_cost >= 0 AND total_cost < 'Infinity'::numeric "
            "AND total_cost = uncached_input_cost + cached_input_cost "
            "+ output_cost + reasoning_cost) "
            "OR (status <> 'calculated' AND total_cost IS NULL "
            "AND uncached_input_cost IS NULL AND cached_input_cost IS NULL "
            "AND output_cost IS NULL AND reasoning_cost IS NULL AND reason_code IS NOT NULL)",
            name="ck_event_costs_result",
        ),
    )
    op.create_index("ix_event_costs_status", "event_costs", ["status"])
    op.create_index("ix_event_costs_model_price_id", "event_costs", ["model_price_id"])
    op.execute("""
        INSERT INTO event_costs (id, usage_event_id, status, uncached_input_tokens,
            cached_input_tokens, regular_output_tokens, reasoning_tokens,
            calculation_version, calculated_at, reason_code, reason_detail)
        SELECT gen_random_uuid(), id, 'unpriced', 0, 0, 0, 0, 'pending', now(),
            'not_calculated', 'Historical event awaits explicit cost calculation'
        FROM usage_events
    """)


def downgrade() -> None:
    # Never relabel v2 payloads: that would invalidate stored idempotency fingerprints.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM usage_events WHERE schema_version = 2) THEN
                RAISE EXCEPTION 'Cannot downgrade while schema v2 events exist'
                    USING HINT = 'Use a disposable database or restore a pre-Module-4 backup';
            END IF;
        END $$
    """)
    op.drop_table("event_costs")
    op.drop_table("model_prices")
    op.execute("DROP FUNCTION protect_model_price_history()")
    cost_status.drop(op.get_bind(), checkfirst=True)
    reasoning_mode.drop(op.get_bind(), checkfirst=True)
    op.drop_constraint("ck_usage_events_token_subsets", "usage_events", type_="check")
    op.drop_constraint("ck_usage_events_schema_version", "usage_events", type_="check")
    op.create_check_constraint(
        "ck_usage_events_schema_version", "usage_events", "schema_version = 1"
    )
    # btree_gist may serve other database objects and is deliberately retained.
