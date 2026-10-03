# AI Profit Monitor

AI Profit Monitor is a production-oriented foundation for tracking AI API usage by customer and feature. Module 1 provides FastAPI, Next.js, PostgreSQL, migrations, and health checks. Module 2 adds password authentication, revocable sessions, and tenant-safe organizations. Module 3 adds projects, project API keys, and privacy-conscious usage-event ingestion. Module 4 adds versioned text-model pricing and deterministic Decimal cost calculation. Revenue, profitability, and analytics dashboards remain deferred.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Node.js 20.9+
- pnpm 10 (`corepack enable` then `corepack prepare pnpm@10.17.1 --activate`)
- Docker Desktop with Docker Compose

All commands below are PowerShell-compatible and start from this directory.

## Run with Docker

From the repository root, start PostgreSQL, the API, and the frontend together:

```powershell
docker compose up -d --build --wait
docker compose ps
```

Open <http://localhost:3000>. API documentation is at <http://localhost:8000/docs>. The API container applies Alembic migrations before starting. If you need custom settings, copy `.env.example` to `.env` first. The browser-facing `NEXT_PUBLIC_API_BASE_URL` is embedded during the web image build, so rebuild the image after changing it.

Stop the stack without deleting PostgreSQL data with `docker compose down`.

## First-time setup

```powershell
Copy-Item .env.example .env

Set-Location apps/api
uv sync --dev

Set-Location ../web
pnpm install --frozen-lockfile
Set-Location ../..
```

The checked-in lockfiles make installs reproducible. Run `uv lock` or `pnpm install` only when intentionally changing dependencies.

## Run locally

Start PostgreSQL and wait for it to become healthy:

```powershell
docker compose up -d --wait postgres
```

Apply migrations and start the backend (terminal 1):

```powershell
Set-Location apps/api
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

Start the frontend (terminal 2):

```powershell
Set-Location apps/web
pnpm dev
```

Open <http://localhost:3000>. API documentation is at <http://localhost:8000/docs>.

Public authentication pages are available at <http://localhost:3000/register> and <http://localhost:3000/login>. The protected application shell is at <http://localhost:3000/app>.

## Projects and usage ingestion

After signing in, open <http://localhost:3000/app/projects>. An organization owner or admin can create a project, open its details, create a named project API key, and revoke keys. Members can view their organization's projects and events. Project slugs remain stable after renaming. A disabled project rejects new ingestion.

The key creation response displays the full key exactly once. Copy it into your integration's secret manager. Subsequent API responses show only the public prefix and metadata; PostgreSQL stores only a SHA-256 hash of the full, high-entropy key. Rotate by creating a new key, updating the integration, and revoking the old one. Dashboard management uses the session cookie; ingestion uses only `Authorization: Bearer <project-key>`.

Single-event ingestion (replace the placeholder key and use a current UTC timestamp):

```powershell
curl.exe -X POST http://localhost:8000/api/v1/ingest/events -H "Authorization: Bearer YOUR_PROJECT_API_KEY" -H "Content-Type: application/json" -d '{"client_event_id":"event-123","schema_version":2,"provider":"openai","model":"gpt-4o-mini","feature":"assistant","status":"success","input_tokens":42,"output_tokens":12,"occurred_at":"2026-10-03T10:00:00Z"}'
```

Batch ingestion sends an `events` array to `/api/v1/ingest/events/batch`:

```powershell
curl.exe -X POST http://localhost:8000/api/v1/ingest/events/batch -H "Authorization: Bearer YOUR_PROJECT_API_KEY" -H "Content-Type: application/json" -d '{"events":[{"client_event_id":"event-124","schema_version":2,"provider":"anthropic","model":"claude-sonnet","feature":"assistant","status":"success","input_tokens":30,"output_tokens":9,"occurred_at":"2026-10-03T10:00:00Z"},{"client_event_id":"event-125","schema_version":2,"provider":"google","model":"gemini-flash","feature":"search","status":"success","input_tokens":20,"output_tokens":5,"occurred_at":"2026-10-03T10:01:00Z"}]}'
```

Required event fields are `client_event_id`, `provider`, `model`, `feature`, `status`, `input_tokens`, `output_tokens`, and timezone-aware `occurred_at`; `schema_version` defaults to `1`. Optional metadata includes `customer_external_id`, `operation`, `cached_input_tokens`, `reasoning_tokens`, `provider_reported_total_tokens`, `duration_ms`, `provider_request_id`, `error_code`, and a bounded flat string map of `tags`. Status is `success`, `error`, `timeout`, or `cancelled`. Providers such as `openai`, `anthropic`, `google`, `azure_openai`, `aws_bedrock`, and `other` are supported as lowercase identifiers. Use schema version 2 for normalized input/cache and output/reasoning subsets; a provider total is never inferred by blindly summing components.

Retries with the same project, `client_event_id`, and normalized payload return the existing event (`200`). A changed payload under the same ID returns `409 duplicate_event_conflict`. Batches are transactional: any invalid or conflicting item rejects the entire batch. Identical repeated IDs inside one batch return one created result and subsequent existing results. The default limits are 100 events per batch, 1 MiB per body, events at most 365 days old or five minutes in the future, and 25 events per query page (maximum 100).

View recent events in the project detail page or call `GET /api/v1/projects/{project_id}/events` with a dashboard session cookie. Filters include `provider`, `model`, `feature`, `customer_external_id`, `status`, `start_time`, and `end_time`; use the returned `next_cursor` for the next page. Event detail is `GET /api/v1/projects/{project_id}/events/{event_id}`. Both endpoints check organization membership.

Ingestion accepts usage metadata only. Prompts, messages, response bodies, documents, embeddings, and other content fields are rejected and are not stored. Prefer an internal opaque customer ID rather than an email address in `customer_external_id`.

## Model pricing and usage costs

Recent Events now shows each event's cost status and auditable breakdown. Costs use the exact active provider/model/currency price effective at `occurred_at`, with no fuzzy model aliases. All money is calculated with Python `Decimal`, stored as PostgreSQL `NUMERIC(38,18)`, and returned as decimal strings. Unknown prices produce `unpriced` with a null total, never an assumed zero. Prices and costs are not fetched from provider websites at request time.

No real provider prices are seeded. A trusted operator imports verified catalog records with provenance; organization owners cannot edit the shared global catalog. From `apps/api`:

```powershell
uv run python -m app.cli.pricing import C:/path/to/verified-prices.json
uv run python -m app.cli.pricing import C:/path/to/new-prices.json --close-previous
```

For local experimentation, `../../docs/examples/prices.example.json` contains explicitly fictional prices for `example / text-demo-v1`. Importing it never configures prices for OpenAI, Anthropic, or other real providers. The migration requires PostgreSQL's `btree_gist` extension to prevent concurrent overlapping active price intervals.

New integrations should explicitly send `schema_version: 2`: input includes cached input, output includes reasoning, and each subset must be no larger than its total. The provider-reported total is informational. Version 1 remains accepted with unchanged fingerprints/defaults; historical v1 events with nonzero cached/reasoning counters have ambiguous semantics and remain unsupported rather than being silently reinterpreted.

`GET /api/v1/projects/{project_id}/events` and event detail include cost components, status/reason, calculation version/time, and the exact pricing record. `GET /api/v1/pricing/models` exposes the versioned catalog to authenticated dashboard users. `COST_CURRENCY` defaults to USD and never performs currency conversion.

Changing the catalog and retrying ingestion do not rewrite saved costs. Owners/admins may explicitly recalculate up to 100 event IDs via `POST /api/v1/projects/{project_id}/events/recalculate` with body `{"event_ids":["EVENT_UUID"],"replace_calculated":false}` and a trusted Origin header. Existing calculated snapshots are skipped unless `replace_calculated` is explicitly true. A CLI equivalent supports operator backfills. Existing historical events receive an unpriced placeholder until selected for recalculation.

See [model pricing and costs](docs/model-pricing.md) for the precise formulas, reasoning/cache rules, operator commands, version compatibility, downgrade safeguards, and unsupported dimensions. Prompts/responses remain rejected; only usage metadata and its cost are stored.

## Authentication and organizations

Registration creates the user, organization, owner membership, and initial session in one PostgreSQL transaction. Passwords are hashed with Argon2id. Authentication uses a random opaque token sent only through an HttpOnly cookie; PostgreSQL stores only its SHA-256 digest. Logout deletes the active session and clears the cookie. Organization routes always resolve membership server-side and inaccessible organizations return `404`.

Browser requests use `credentials: "include"`. `CORS_ORIGINS` must list the exact frontend origins, and cookie-authenticated `POST`/`PATCH` requests must carry a matching `Origin` or `Referer`. In production set `APP_ENV=production`, `SESSION_COOKIE_SECURE=true`, and serve frontend/API over HTTPS. Organization slugs remain stable when names change.

Example registration with a cookie jar:

```powershell
curl.exe -c cookies.txt -H "Content-Type: application/json" -H "Origin: http://localhost:3000" -d '{"email":"owner@example.com","password":"a-secure-passphrase","display_name":"Owner User","organization_name":"Acme AI"}' http://localhost:8000/api/v1/auth/register
curl.exe -b cookies.txt http://localhost:8000/api/v1/auth/me
curl.exe -b cookies.txt -H "Origin: http://localhost:3000" -X POST http://localhost:8000/api/v1/auth/logout
```

## Quality checks

Backend:

```powershell
Set-Location apps/api
uv run ruff format --check .
uv run ruff check .
uv run mypy app tests
uv run pytest
```

Authentication integration tests use a real PostgreSQL database named `ai_profit_monitor_test`. Create and migrate it once before running the suite:

```powershell
docker exec ai-profit-monitor-postgres-1 createdb -U ai_profit_monitor ai_profit_monitor_test
$env:DATABASE_URL="postgresql+asyncpg://ai_profit_monitor:local_development_only@localhost:5437/ai_profit_monitor_test"
Set-Location apps/api
uv run alembic upgrade head
uv run pytest
```

Frontend:

```powershell
Set-Location apps/web
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

## Configuration

Configuration is read from environment variables and the root `.env` file. `APP_ENV` accepts `development`, `test`, or `production`. CORS origins are a JSON array. Session cookie name, lifetime, Secure flag, SameSite behavior, optional domain, last-used write interval, password minimum, and development login throttling are configurable; see `.env.example`. Browser-visible configuration must use the `NEXT_PUBLIC_` prefix and must never contain secrets.

## Service checks

- `GET /health` reports process health without touching PostgreSQL.
- `GET /ready` runs a lightweight `SELECT 1`; it returns HTTP 503 when PostgreSQL is unavailable.

Stop local infrastructure without deleting data with `docker compose down`. The `postgres_data` named volume persists database data.

## Known limitations and deferred work

- The login limiter is process-local and only a development safeguard. Production needs a shared distributed limiter at the edge or in later infrastructure.
- Ingestion has body, batch, and field limits, but production still needs distributed rate limiting at an application gateway or a later shared service. No in-memory limiter is claimed as production safe.
- OAuth, MFA, email verification, password reset, invitations, and email delivery are deferred authentication hardening work.
- Provider integrations, SDKs, customers, revenue/profitability, Redis/Celery, billing, and analytics dashboards remain deferred. Costs support standard text tokens only; unsupported dimensions produce an unavailable cost with a reason.

See [the authentication design](docs/authentication.md) and [the usage-ingestion design](docs/usage-ingestion.md) for lifecycle, tenant, privacy, and idempotency decisions.

