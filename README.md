# Smart Money Monitor

A web dashboard that tracks SEC Form 4 insider transactions and 13F institutional holdings for a
watchlist of US equities, turns them into dollar-weighted signals, and keeps itself current from
SEC EDGAR, Alpaca, Finnhub and yfinance.

Requirements: [`docs/SRS.md`](docs/SRS.md) · Plan: [`docs/TIMELINE.md`](docs/TIMELINE.md) ·
TradingView decision: [`docs/TRADINGVIEW.md`](docs/TRADINGVIEW.md) and
[`docs/adr/003-chart-library.md`](docs/adr/003-chart-library.md).

Data flows one way: **providers → ingestion jobs → parsers → store → signal engine → API → React UI**.
The API never calls a provider in the request path.

## Stack

| Layer | Choice |
| --- | --- |
| API | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 async |
| Jobs | APScheduler with a DB lock, NYSE calendar (`exchange_calendars`) |
| Storage | SQLite (dev) or PostgreSQL (Compose), Alembic migrations |
| Frontend | React 18, Vite, TypeScript, Tailwind, TanStack Query, Recharts |
| Packaging | Docker Compose (`ops/docker-compose.yml`) |

## Quick start

```bash
cd backend
uv sync
cp ../ops/.env.example .env          # fill in SEC_USER_AGENT; other keys optional
uv run alembic upgrade head
uv run uvicorn app.main:app --reload # http://localhost:8000/api/docs
```

```bash
cd frontend
pnpm install
pnpm dev                             # http://localhost:5173, proxies /api to :8000
```

Everything in containers: `docker compose -f ops/docker-compose.yml up --build`.

## Configuration

`ops/.env.example` documents every variable. Secrets stay in `.env`; the only required value to
start is `SEC_USER_AGENT` with a contact email. `smm.yaml` holds the watchlist, lookback, cadences
and provider order, so operators can tune them without code changes.

Providers degrade gracefully: each has a rate limiter and a circuit breaker (open after five
consecutive failures, half-open after five minutes), every chain falls back in configured order, and
every stored row records its `source`. If all providers fail, read endpoints keep serving last-good
data with a stale flag.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/dashboard` | Signals, quotes, tape, freshness |
| GET | `/api/history/{ticker}` | Daily closes (6 months by default) |
| GET | `/api/holders/{ticker}` | Top 13F holders |
| POST | `/api/refresh` | Immediate run, 202, throttled to once per 30 s |
| GET, PUT | `/api/watchlist` | Read or replace the watchlist (PUT needs the admin token from non-local hosts) |
| GET | `/healthz`, `/readyz`, `/metrics` | Health, readiness, Prometheus |

Response shapes are the TypeScript types in `docs/SRS.md` §7.2, mirrored in
`frontend/src/api/types.ts` and asserted by `backend/tests/contract/test_api.py`.

## Checks

```bash
cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest -q
cd frontend && pnpm lint && pnpm typecheck && pnpm test -- --run && pnpm build
```

Unit and contract tests run offline: HTTP is mocked at the adapter boundary or replayed from
`backend/tests/fixtures/form4/`. Integration tests (`-m integration`) hit real providers and are
opt-in.

## Status against the timeline

- **P0** — layout, tooling, CI, Compose, ADR-001/002/003, Form 4 fixtures: done.
- **P1** — schema and Alembic migration, EDGAR client, Form 4 parser, classification, idempotent
  ingestion, run logging: done.
- **P2** — quotes, bars, holders adapters, signal engine, API contract, contract tests: done.
- **P3** — scheduler, market-hours guards, DB lock, freshness/stale flags: done; soak test pending.
- **P4** — dashboard (tiles, tape, chart, holders, freshness, disclaimer, states): done; visual and
  axe review pending.
- **P5** — SSE quote stream and new-filing toasts, watchlist API and editor: done. Alerts,
  cluster/10b5-1 flags and SEC 13F data sets: not started.
- **P6** — load/failure tests, deployment: not started.

UI-14 is descoped for v1.0: the Advanced Charts licence fails for a personal dashboard in a public
repository (ADR-003). UI-06 stays on Recharts and is the authoritative marker geometry.
