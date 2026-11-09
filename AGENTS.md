# AGENTS.md — Smart Money Monitor

Instructions for AI coding agents (and humans) working in this repository.
The authoritative requirements are in `docs/SRS.md`; the plan is in `docs/TIMELINE.md`; the
TradingView chart plan is in `docs/TRADINGVIEW.md`.
When this file and the SRS disagree, the SRS wins. Update this file whenever a convention changes.

## 1. What this project is

A web dashboard that tracks SEC Form 4 insider transactions and 13F institutional holders for a
watchlist of US equities (default: NVDA, AAPL, TSLA, AMZN, META, AMD, PLTR, COIN), turns them into
dollar-weighted signals, and keeps itself up to date from yfinance, SEC EDGAR, Alpaca and Finnhub.
TradingView is used for presentation only (widgets / Lightweight Charts), never as a data source.

Data flow (one direction only):

    providers -> ingestion jobs -> parsers/normalisers -> store -> signal engine -> API -> React UI

**The API never calls a provider in the request path.** Providers feed the store on a schedule; the
API reads the store.

## 2. Repository layout

    smart-money-monitor/
    ├─ AGENTS.md
    ├─ docs/                  SRS.md, TIMELINE.md, TRADINGVIEW.md, adr/NNN-title.md
    ├─ backend/
    │  ├─ pyproject.toml
    │  ├─ app/
    │  │  ├─ main.py          FastAPI app factory
    │  │  ├─ config.py        pydantic-settings; env + YAML
    │  │  ├─ api/             routers, response models (Pydantic)
    │  │  ├─ core/            market calendar, rate limiter, circuit breaker, logging
    │  │  ├─ db/              SQLAlchemy models, session, alembic/
    │  │  ├─ providers/       base.py (interfaces), sec_edgar.py, alpaca.py, finnhub.py, yfinance_.py
    │  │  ├─ parsers/         form4.py, thirteenf.py
    │  │  ├─ services/        classification.py, signals.py, freshness.py
    │  │  └─ jobs/            scheduler.py, quotes.py, form4.py, bars.py, holders.py
    │  └─ tests/              unit/, contract/, integration/, fixtures/form4/*.xml
    ├─ frontend/              Vite + React + TypeScript + Tailwind + shadcn/ui + TanStack Query + Recharts
    │                          src/chart/ holds the optional TradingView datafeed (UI-14)
    └─ ops/                   Dockerfile(s), docker-compose.yml, .env.example

## 3. Setup and commands

Backend (Python 3.12, uv):

    cd backend
    uv sync
    cp ../ops/.env.example .env           # fill in keys; see section 7
    uv run alembic upgrade head
    uv run uvicorn app.main:app --reload  # http://localhost:8000
    uv run pytest -q                      # unit + contract; no network
    uv run pytest -m integration          # hits real providers; opt-in only
    uv run ruff check . && uv run ruff format --check .
    uv run mypy app

Frontend (Node 20+, pnpm):

    cd frontend
    pnpm install
    pnpm dev                              # http://localhost:5173, proxies /api to :8000
    pnpm test && pnpm lint && pnpm typecheck && pnpm build

Charting Library files are copied from TradingView's private repository into a git-ignored
`frontend/public/charting_library/` at build time; never commit them (see the TradingView plan).

Everything: `docker compose -f ops/docker-compose.yml up --build`

Before opening a PR, run the backend and frontend checks above. CI runs the same commands.

## 4. Code style and conventions

- Python: type hints everywhere, mypy clean, ruff for lint and format, `async` for I/O.
- Money and share counts: `Decimal` in the backend, never `float`. Serialise to JSON numbers at the edge.
- Time: store UTC. Trading dates and market hours use `America/New_York` and the NYSE calendar
  (holidays and early closes). Never compare naive datetimes.
- HTTP: use the shared `httpx` client factory (timeouts, retries with backoff, per-provider rate limiter).
  Do not call `requests`, raw `urllib`, or a provider SDK directly from jobs, services or routes.
- Provider SDKs and HTTP details live only in `app/providers/`. Everything else depends on the
  interfaces in `providers/base.py` (`QuoteProvider`, `BarProvider`, `InsiderProvider`, `HolderProvider`).
- Every stored row records its `source` (provider name). Every job run is recorded in `ingest_run`.
- Writes are idempotent. Insider rows upsert on `(accession_no, line_no)`; amendments (Form 4/A) supersede originals.
- TypeScript: strict mode, no `any`, components are small and typed from the API models in `frontend/src/api/types.ts`.
- Frontend numbers use tabular numerals; compact currency is `$K/$M/$B/$T`, net values are signed, null shows `—`.
- Commits: small and focused, imperative mood. PR titles end with the requirement IDs they satisfy, e.g. `Add Form 4 parser (ING-03, SIG-02)`.

## 5. Domain rules (high stakes — do not change without a test and an SRS reference)

Classification (SRS 6.2):

| Code | typeLabel | action | counts toward signals |
|------|-----------|--------|-----------------------|
| P | Open-market buy | buy | yes |
| S | Open-market sell | sell | yes |
| A | Award / grant | other | no |
| M, X, C | Option exercise / conversion | other | no |
| F | Tax withholding | other | no |
| G | Gift | other | no |
| D | Disposed to issuer | other | no |
| anything else | Other | other | no |

Signals (SRS 5.2):

- `value = shares × price`; `null` when no price is reported.
- `netValue = Σ buy value − Σ sell value` over the lookback window (default 6 months), open-market rows only.
- `txnCount` = number of buy + sell rows. `starredCount` = open-market buys by a CEO or CFO.
- Tile emphasis is **sign-aware**: |net| ≥ $10M strong, ≥ $1M moderate; positive uses the buy colour, negative the sell colour.
- Non-open-market rows are displayed dimmed and excluded from signals.
- Rule 10b5-1 sales are flagged, never silently dropped.

Never do any of the following:

- Add order placement or any Alpaca trading endpoint. Keys are data-only.
- Scrape TradingView or any site whose terms prohibit it. Use official APIs, EDGAR, or documented libraries.
- Commit, redistribute or modify the TradingView Charting Library files, or hide its attribution.
- Remove or weaken the footer disclaimer ("For information only — not investment advice") or phrase output as a recommendation.
- Convey buy/sell by colour alone. Keep ▲/▼ and +/− signs.

## 6. Data sources and etiquette

| Need | Primary | Fallbacks |
|------|---------|-----------|
| Form 4 insider txns | SEC EDGAR (submissions JSON + filing XML) | Finnhub insider transactions, yfinance `insider_transactions` |
| Quotes | Alpaca market data | Finnhub quote, yfinance `fast_info` |
| Daily bars | Alpaca bars | yfinance `history` |
| 13F holders | yfinance `institutional_holders` (MVP) | SEC Form 13F data sets, Finnhub if plan allows |
| Ticker to CIK | SEC `company_tickers.json` | Finnhub profile |

- SEC EDGAR: always send `User-Agent: <name> <email>` from `SEC_USER_AGENT`; stay at or under 5 requests/second
  (the SEC limit is 10). Cache aggressively; filings are immutable once accepted.
- Keep provider limits (rate, real-time vs delayed, premium-only endpoints) in config, not code. Stay under 50% of any documented limit.
- yfinance is unofficial and breaks without notice. Pin its version, isolate it in its adapter, and never let it be the only source for a data type.
- Fallback chain: on error, timeout or empty result try the next provider; the circuit breaker opens after 5 consecutive failures and half-opens after 5 minutes.
- If every provider fails, serve last-good data from the store with a stale flag. Never return a 5xx from a read endpoint because a provider is down.

## 7. Secrets and configuration

- Keys live in environment variables or `.env` (git-ignored). Required: `SEC_USER_AGENT`, `ALPACA_KEY_ID`,
  `ALPACA_SECRET_KEY`, `FINNHUB_API_KEY`, `ADMIN_TOKEN`, `DATABASE_URL`.
- Never commit secrets, never log them, never send them to the browser. Update `ops/.env.example` when adding a variable.
- `CHARTING_LIBRARY_TOKEN` is a build-time, read-only token for the private Charting Library repository.
  It is never a runtime variable and never reaches the browser bundle.
- Watchlist, lookback, cadences and provider order are configurable (YAML + env); do not hard-code tickers outside defaults.

## 8. Testing instructions

- Unit and contract tests must run offline. Mock HTTP at the adapter boundary or replay recorded fixtures.
- `backend/tests/fixtures/form4/` holds real Form 4 XML files (joint filers, 10b5-1, amendments, derivative-only). Every parser bug gets a new fixture first, then the fix.
- Required coverage: at least 85% on `parsers/` and `services/`.
- Contract tests assert the response shapes in SRS 7.2; changing a shape means updating the contract tests, the frontend types and the SRS in the same PR.
- Market-calendar tests must include Thanksgiving, Christmas, New Year and early-close days.
- Frontend: component tests for tiles, tape filters, chart markers and empty/error states; an axe accessibility scan in `e2e/a11y.spec.ts` covering populated, panel, loading, empty and stale states, plus keyboard coverage in `e2e/keyboard.spec.ts`. Both run in the Playwright suite; never disable an axe rule or exclude an element to pass.
- Integration tests (marked `integration`) may call real providers and are never required in CI.

## 9. Auto-update behaviour (SRS 5.4)

| Job | Market hours | Off-hours |
|-----|--------------|-----------|
| Quotes | every 15-30 s | every 15 min on trading days |
| Form 4 poll | every 5 min | every 5 min until 22:00 ET weekdays, hourly otherwise |
| Daily bars | gap-fill at start-up | 16:30 ET each trading day |
| 13F holders | daily; hourly near filing deadlines | same |
| Signals | event-driven after insider ingest | same |

Jobs run once across restarts and replicas (DB lock) and are safe to re-run. The UI refetches the dashboard
every 60 s and pauses when the tab is hidden.

## 10. Agent roles

Use these roles to scope work. An agent stays inside its role unless the task explicitly crosses a boundary;
cross-boundary changes go in separate commits or PRs.

| Role | Owns | Must not touch | Done when |
|------|------|----------------|-----------|
| **Ingestion agent** | `providers/`, `jobs/`, rate limiters, circuit breakers, fallbacks | API routes, UI | Adapter has interface tests, honours limits, records `source` and `ingest_run` |
| **Parser agent** | `parsers/`, `tests/fixtures/` | Provider HTTP code | Golden-file tests pass; new edge case has a fixture |
| **Signals agent** | `services/classification.py`, `services/signals.py` | Provider code | Rules in section 5 covered by unit tests; SRS reference cited |
| **API agent** | `api/`, Pydantic models, OpenAPI, SSE | Parsing and classification rules | Contract tests green; no provider call in request path |
| **Scheduler agent** | `jobs/scheduler.py`, `core/` calendar, DB lock, freshness | UI | Soak run clean; start-up gap-fill verified; holiday tests pass |
| **Frontend agent** | `frontend/` | Backend rules; may not invent API fields | Matches design tokens; keyboard operable; axe clean; stale/empty/error states present |
| **QA agent** | tests, reconciliation scripts, load and failure-injection tests | Production code, except to add test hooks | AC-01 to AC-08 reproducible from one command |
| **Compliance reviewer** | provider-terms notes, disclaimers, secrets review | Feature code | Terms reviewed per provider; disclaimer present; no secrets in repo or client bundle |

## 11. Design tokens (frontend)

Dark theme: background `hsl(160 27% 6%)`, card `hsl(157 25% 10%)`, text `hsl(150 16% 91%)`,
border `hsl(150 24% 16%)`, muted `hsl(153 9% 54%)`, champagne/primary `hsl(45 51% 70%)`,
buy `hsl(145 63% 49%)`, sell `hsl(6 53% 49%)`.
Fonts: Cormorant Garamond (display), Inter (UI). Small-caps labels with 0.12em tracking.

## 12. Definition of done

A change is done when: it satisfies the cited requirement IDs; lint, type checks and tests pass; new behaviour has
tests; the SRS, `.env.example` and this file are updated if affected; no secrets or provider SDK leaks outside
their layer; and the UI still shows data freshness and the disclaimer.

## 13. When unsure

Prefer EDGAR over third-party aggregators for insider data. Prefer a small, tested change over a broad one.
If a provider limit, term of service or endpoint availability is unclear, stop and record the question in
`docs/adr/` instead of guessing.
