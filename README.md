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

## Deployment

The production stack is `ops/docker-compose.yml` (`api`, `web`, `db`); operations are documented in
[`docs/RUNBOOK.md`](docs/RUNBOOK.md). Copy `ops/.env.example` to `ops/.env`, set `SEC_USER_AGENT` and
`ADMIN_TOKEN` (Compose refuses to start without them), then:

```bash
docker compose -f ops/docker-compose.yml up -d --build
```

The API image runs `alembic upgrade head` before uvicorn starts, so an empty database volume is
migrated on first boot, and `web` waits for the API's `/readyz` health check. nginx serves the
hashed production bundle with SPA fallback and proxies `/api`, `/healthz`, `/readyz` and `/metrics`,
so `http://localhost:3000/healthz` answers on the same origin as the dashboard.
`ENVIRONMENT=production` makes the API fail fast when `SEC_USER_AGENT` lacks a contact email,
`ADMIN_TOKEN` is empty, or `CORS_ORIGINS` contains a wildcard.

CI builds both images and validates the Compose file. The deployed shape is also exercised without
Docker: `cd frontend && pnpm smoke:deploy` builds the production bundle, applies migrations to an
empty SQLite database, seeds the fixture data through the real ingest path, serves the bundle with
the same proxied paths, and checks health, hashed assets, SPA fallback, the dashboard and the axe
scan.

## SEC bulk backfill

Historical SEC data sets are loaded from a local ZIP archive or an extracted directory; no provider
credentials or network calls are involved. Both commands accept `--symbols` to restrict the load
and `--database-url` to override `DATABASE_URL`.

```bash
cd backend
uv run python scripts/load_sec_bulk.py insider --path /data/insider_transactions.zip
uv run python scripts/load_sec_bulk.py 13f --path /data/form_13f.zip \
  --cusip-map /data/cusip-map.csv
```

The 13F loader resolves issuers by CUSIP when a `cusip,symbol` map is supplied and otherwise falls
back to the stored company name. `GET /api/holders/{ticker}` returns the latest report period only.

## EDGAR reconciliation

AC-01 compares the stored Form 4 rows with a frozen EDGAR-shaped snapshot: five sampled filings for
each of the eight watchlist tickers (40 total). Every filing is re-parsed with the same
`parse_form4` parser ingestion uses, then shares, price, code, date and owner are compared with the
values the snapshot claims. The fixtures live in `backend/tests/fixtures/reconciliation/`; no
provider credentials or network calls are involved.

```bash
cd backend
uv run python scripts/reconcile_edgar.py \
  --snapshot tests/fixtures/reconciliation/edgar_snapshot.json
```

The run is recorded as an `edgar_reconciliation` job and each difference is persisted in
`reconciliation_mismatch`; the command exits non-zero when any field differs. The latest run is
served by `GET /api/data-quality` and shown in the Data Quality panel.

## Load test

AC-05 measures NFR-01 against a running backend. The harness models 50 concurrent browser users:
each client requests `/api/dashboard` three times, waits a 1 s think time between requests, and
successive clients start 20 ms apart so the run reflects a user population rather than one
synchronised burst. It warms the endpoint first and reports throughput plus p50/p95/p99 latency.
The gate is p95 ≤ 300 ms with zero failed requests; the command exits non-zero otherwise. It only
reads the API, so no provider credentials or external network calls are involved.

```bash
cd backend
uv run python scripts/load_test.py --url http://127.0.0.1:8010 \
  --users 50 --requests 3 --think-time-ms 1000 --ramp-ms 20
```

`--think-time-ms 0 --ramp-ms 0` turns the same harness into a raw burst measurement, and
`--max-p95-ms` moves the budget. The E2E suite runs this command against the seeded server on port
8010 and then re-checks the endpoint from a real browser.

## Provider failure drill

AC-03 and AC-04 are exercised against the seeded database by
`backend/scripts/e2e_failure_drill.py`, which injects a provider fault instead of mocking a
successful call:

```bash
cd backend
uv run python scripts/e2e_failure_drill.py --mode fallback   # primary provider disabled
uv run python scripts/e2e_failure_drill.py --mode outage     # every provider fails
```

`fallback` builds a two-provider quote chain, disables the primary through the same configuration
the registry applies (`DISABLED_PROVIDERS`, or `disabled_providers` in `smm.yaml`), and runs one
real ingest cycle: quotes are written by the fallback and each tile shows that source. `outage`
fails every provider, proves the last-good quotes are kept, and ages them past the freshness window
so the UI shows the stale badge without an error page. Neither mode touches the network.

## Accessibility

WCAG 2.1 AA (NFR-07, AC-07) is enforced by `frontend/e2e/a11y.spec.ts`, which runs axe-core
(`@axe-core/playwright`, WCAG 2.1 A/AA tags) against the real dashboard on the seeded backend in
five states: populated, the alert/data-quality/watchlist panels open, the loading skeleton, an
empty watchlist, and last-good quotes left stale by a genuine provider outage. Serious and critical
findings fail the suite, and no rule is disabled and no element excluded. `frontend/e2e/keyboard.spec.ts`
walks the tab order with real key presses, asserting a visible focus ring at every stop and that
tiles, tape filters, the 10b5-1 toggle and the watchlist editor work without a mouse. `pnpm a11y`
runs both files; `pnpm e2e` includes them in the full browser suite.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/dashboard` | Signals, quotes, tape, freshness; `?exclude10b5_1=true` excludes plan sales |
| GET | `/api/history/{ticker}` | Daily closes (6 months by default) |
| GET | `/api/holders/{ticker}` | Top 13F holders |
| POST | `/api/refresh` | Immediate run, 202, throttled to once per 30 s |
| GET, PUT | `/api/watchlist` | Read or replace the watchlist (PUT needs the admin token) |
| GET | `/api/alerts` | Recent deduplicated ADM-03 alert history |
| GET | `/api/data-quality` | Insider cross-check, EDGAR reconciliation and SEC bulk-load status |
| GET | `/healthz`, `/readyz`, `/metrics` | Health, readiness, Prometheus |

Response shapes are the TypeScript types in `docs/SRS.md` §7.2, mirrored in
`frontend/src/api/types.ts` and asserted by `backend/tests/contract/test_api.py`.

## Checks

```bash
cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest -q
cd frontend && pnpm lint && pnpm typecheck && pnpm test -- --run && pnpm build
cd frontend && pnpm a11y
cd frontend && pnpm smoke:deploy
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
- **P4** — dashboard (tiles, tape, chart, holders, freshness, disclaimer, states): done; visual
  parity review (AC-06) pending.
- **P5** — SSE quote stream and new-filing toasts, watchlist API and editor, cluster-buy flag
  and 10b5-1 badge with exclusion toggle, alerts to email/Telegram/webhook with persisted
  history, SEC insider/13F bulk backfills, and the daily second-provider insider cross-check:
  done.
- **P6** — EDGAR Form 4 reconciliation (AC-01), the NFR-01 load test (AC-05), provider failure
  injection (AC-03, AC-04), the accessibility scan (AC-07) and deployment (production images,
  migrations on start, health checks, runbook, smoke test): done; release notes and the v1.0 tag
  remain.

UI-14 is descoped for v1.0: the Advanced Charts licence fails for a personal dashboard in a public
repository (ADR-003). UI-06 stays on Recharts and is the authoritative marker geometry.
