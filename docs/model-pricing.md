# Versioned model prices and event costs

Module 4 calculates standard text-token costs, with no provider network calls. No production prices are bundled or guessed. Operators import verified price records, including their source and effective time. An empty catalog produces `unpriced` costs with a null total. The sample catalog under `docs/examples/` uses a fictional provider/model and explicitly synthetic rates.

## Token schema and Module 3 compatibility

Module 3 documented token fields as independent counters. Reinterpreting stored payloads or changing their fingerprints would break both billing correctness and retries. Its `schema_version: 1` therefore remains accepted and remains the default for clients that omit the version. Existing v1 fingerprints and payloads are unchanged.

New integrations should explicitly send `schema_version: 2`. Here `input_tokens` includes cached input and `output_tokens` includes reasoning. Both subset inequalities are enforced in the request schema and PostgreSQL. Integrations whose provider reports separate counters must normalize them into these totals before submitting. `provider_reported_total_tokens` remains informational and is never used for billing.

For v1, events with both cached and reasoning counters zero have unambiguous totals and may be calculated. Any v1 event with either counter nonzero is `unsupported / legacy_token_semantics`; no values or fingerprints are rewritten. Fixing historical ambiguous semantics requires a separate, reviewed data migration, not the recalculation endpoint. A v1 retry is still an idempotent success; changing its version under the same client event ID remains a 409.

Migration 0004 creates a `not_calculated` placeholder for preexisting events. Operators explicitly recalculate selected historical events after importing appropriate prices. It does not price historical data silently. Downgrade removes the new cost/catalog tables while preserving v1 events and Module 2 data. It safely refuses to downgrade if any v2 events exist, because Module 3 cannot accept their schema. Use a disposable database for rollback verification or restore a pre-Module-4 backup; do not relabel v2 rows. The shared `btree_gist` extension is retained on downgrade.

## Price catalog and effective time

`ModelPrice` stores exact lowercase provider/model names, an uppercase three-letter ISO-style currency code, per-million rates, reasoning mode, `[effective_from, effective_to)` timestamps, provenance, catalog version, and active status. Currency syntax is checked; no exchange-rate conversion or currency guessing occurs. `COST_CURRENCY` defaults to `USD`; a missing USD price never falls back to another currency. Model aliases and fuzzy matching are not used. Event model spelling remains unchanged for idempotency; only lookup is case-normalized.

Prices are `NUMERIC(24,12)`, nonnegative and bounded at 1,000,000,000 per million tokens. Inputs must be exact decimal strings or exact integers/Decimals. The operator JSON reader uses `Decimal` for numeric literals; Python floats, NaN, infinity, and excess precision are rejected. Null cached-input pricing means unknown, not a free cache or an assumed full-input rate. A cached rate is required only when cached tokens are nonzero. A reasoning rate is required exactly when the mode is `separately_priced`.

A PostgreSQL GiST exclusion constraint with `btree_gist` prevents overlapping active intervals for each provider/model/currency, including concurrent writes. A B-tree index supports catalog lookup. This follows PostgreSQL's [range exclusion constraint design](https://www.postgresql.org/docs/16/rangetypes.html#RANGETYPES-CONSTRAINT). Installing `btree_gist` requires an appropriately privileged migration user.

A database trigger prevents changes to a price's rates, identity, provenance, or effective start. Only shortening its effective end or retiring it is allowed. New rates always receive a new record/UUID. Referenced prices cannot be deleted. The import tool serializes catalog mutations and optionally closes a previous interval in the same transaction; failures roll the entire import back. It does not modify `EventCost` rows.

## Deterministic formula

Let U = input minus cached input, C = cached input, O = output minus reasoning, and R = reasoning. Each component cost is `Decimal(tokens) * Decimal(rate) / Decimal("1000000")`.

- Uncached input uses the input rate; cached input uses its explicitly supplied rate.
- `separately_priced`: O uses the output rate and R uses the separate reasoning rate.
- `included_in_output`: O and R both use the output rate. The breakdown allocates a portion of the output bill to reasoning; it is not an extra charge. Together these components equal total output times the output rate.
- `not_supported`: any nonzero reasoning count makes the whole event unsupported. Zero reasoning is allowed.

The total is the sum of the four disjoint components. For the synthetic sample, 1,000 input (including 200 cached) and 500 output (including 100 reasoning) cost `0.0016 + 0.0001 + 0.0016 + 0.0006 = 0.0039 USD`. Provider-reported totals and event status do not alter the formula: an error/timeout may still have consumed tokens. An unknown model with zero tokens is still unpriced.

All arithmetic uses a private Decimal context with precision 60. Rate scale 12 divided by one million requires at most 18 fractional places, stored exactly in `NUMERIC(38,18)`. There is no cent rounding, floating-point conversion, or frontend arithmetic on monetary values. Responses serialize money as decimal strings; the UI only trims insignificant trailing zeros and preserves tiny amounts.

## Unsupported dimensions

Only plain text usage is eligible. Omitted operation or `chat`, `completion`, `completions`, `text`, `text_generation`, `generate_text` are accepted for pricing. Other operations produce `unsupported_operation`. Tags declaring non-text `modality`, `input_modality`, or `output_modality` produce `unsupported_pricing_dimension`.

Reserved unsupported pricing tags include `cache_write_tokens`, `cache_creation_input_tokens`, `image_tokens`, `audio_tokens`, `video_tokens`, `tool_calls`, `tool_call_fees`, `web_search`, `storage`, `fine_tuning`, `batch`, `batch_discount`, `service_tier`, `pricing_tier`, `region`, `enterprise_pricing`, `committed_use`, and `unsupported_pricing_dimensions`. Their presence conservatively makes the whole cost unavailable, rather than presenting an incomplete total. Arbitrary extra top-level event fields remain rejected. Integrators must declare unsupported usage using these indicators; metadata alone cannot detect undisclosed provider fees. Operators must not import flat text rates for models whose price depends on dimensions this schema cannot represent (such as context-length tiers).

Image/audio/video, storage, tools/search fees, fine-tuning, cache-write, batch discounts, contract rates, currency conversion, SDKs, revenue, profit, alerts, recommendations, and analytics dashboards remain outside scope.

## Cost records, transactions, and recalculation

`EventCost` has a unique usage-event FK and holds status, currency, normalized counts, exact component/total amounts, model-price FK, calculation version, timestamp, and stable reason codes. A calculated result requires its pricing reference and valid nonnegative components equal to the total. Noncalculated results require a reason and null monetary values. Tenant access always goes through the parent project's existing authorization.

First ingestion resolves prices by `occurred_at` and creates costs inside the event transaction, using batched lookups/inserts. A failure rolls back new events and costs together. An idempotent retry returns the existing event without recalculating even if prices have since been imported or retired. PostgreSQL uniqueness protects concurrent retries. Expected missing/unsupported prices do not reject usage ingestion.

`POST /api/v1/projects/{project_id}/events/recalculate` requires an owner/admin session plus the existing trusted-origin check. Body: `{"event_ids":["UUID"],"replace_calculated":false}`. At most 100 unique explicit IDs are allowed. A foreign/missing event rejects the whole operation with 404. Event rows are locked in UUID order to serialize concurrent recalculations. By default, calculated snapshots are skipped. `replace_calculated: true` explicitly replaces them, including with an unavailable result if the current catalog no longer supports the event. Existing currency is retained, and `occurred_at` still selects the price. The row's ID stays stable; its version, timestamp, references and amounts are refreshed. Prior cost revisions are not retained: export a snapshot first if that history is needed. This bounded operation is also available to trusted database operators via the CLI.

Event list/detail responses include `cost`, the selected price/rates/provenance, and reasons. Reads never trigger recalculation. `GET /api/v1/pricing/models` requires a dashboard session, supports exact provider/model/currency filters, optional timezone-aware `at`, and bounded `limit`/`offset`. Without `at`, it includes retained inactive history. There is no tenant-accessible write API for the shared catalog; organization admins are not platform pricing administrators.

## Operator commands

From `apps/api`, import a JSON array of verified records (1–100 entries, maximum 1 MiB):

```powershell
uv run python -m app.cli.pricing import C:/path/to/verified-prices.json
uv run python -m app.cli.pricing import C:/path/to/new-version.json --close-previous
uv run python -m app.cli.pricing retire PRICE_UUID
uv run python -m app.cli.pricing recalculate --project-id PROJECT_UUID --event-id EVENT_UUID
uv run python -m app.cli.pricing recalculate --project-id PROJECT_UUID --event-id EVENT_UUID --replace-calculated
```

Local demonstration only: `uv run python -m app.cli.pricing import ../../docs/examples/prices.example.json`, then ingest provider `example`, model `text-demo-v1`, schema version 2. Nothing imports this automatically. Importing overlapping entries fails safely, including repeating the same file. For a corrected historical rate, explicitly retire the old record and import a new version; existing costs stay unchanged until explicitly replaced. Protect access to these operator commands and database credentials.
