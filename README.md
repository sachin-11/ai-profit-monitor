# AI Profit Monitor

Module 1 establishes a production-oriented local foundation for tracking AI API cost by customer and feature. It contains a FastAPI service, a Next.js status page, PostgreSQL infrastructure, migration tooling, and tests. No business-domain functionality is included yet.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Node.js 20.9+
- pnpm 10 (`corepack enable` then `corepack prepare pnpm@10.17.1 --activate`)
- Docker Desktop with Docker Compose

All commands below are PowerShell-compatible and start from this directory.

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

## Quality checks

Backend:

```powershell
Set-Location apps/api
uv run ruff format --check .
uv run ruff check .
uv run mypy app tests
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

Configuration is read from environment variables and the root `.env` file. `APP_ENV` accepts `development` or `test`. CORS origins are a JSON array. Browser-visible configuration must use the `NEXT_PUBLIC_` prefix and must never contain secrets.

## Service checks

- `GET /health` reports process health without touching PostgreSQL.
- `GET /ready` runs a lightweight `SELECT 1`; it returns HTTP 503 when PostgreSQL is unavailable.

Stop local infrastructure without deleting data with `docker compose down`. The `postgres_data` named volume persists database data.

