# Smart Money Monitor 1.0 — release notes

- Version: **1.0.0**
- Tag: **`v1.0`** (annotated; see §7 for the recorded convention)
- Released: 9 November 2026
- Requirements: [`SRS.md`](SRS.md) (AC-01 to AC-10, NFR-01 to NFR-10) · Plan: [`TIMELINE.md`](TIMELINE.md) (P6, M6)

Smart Money Monitor is a self-hosted dashboard for SEC Form 4 insider transactions and 13F
institutional holdings across a watchlist of US equities. This is the first release: the complete
P0–P6 scope of the plan, verified offline against fixtures and a seeded database, with a
production Compose stack and a runbook.

## 1. What ships

**Data pipeline (P0–P2, ING-01 to ING-10).** Provider interfaces for quotes, bars, insiders and
holders; SEC EDGAR submissions and Form 4 XML ingestion with a rate limiter, retries and caching;
a parser covering joint filers, 10b5-1 sales, amendments and derivative-only filings; idempotent
upserts on `(accession_no, line_no)`; six-month backfill and start-up gap-fill; Alpaca, Finnhub and
yfinance adapters with ordered fallback chains, circuit breakers and per-row `source`; a signal
engine for net value, transaction counts and starred CEO/CFO buys; and ingest-run logging.

**API (P2, SRS §7).** `GET /api/dashboard`, `/api/history/{ticker}`, `/api/holders/{ticker}`,
`/api/alerts`, `/api/data-quality`, `GET`/`PUT /api/watchlist`, `POST /api/refresh`, the SSE stream
`/api/stream`, and `/healthz`, `/readyz`, `/metrics`. Contract tests assert the SRS §7.2 shapes.

**Scheduler and resilience (P3, AUT-01 to AUT-07, NFR-02/03).** APScheduler on the cadences in SRS
§5.4, NYSE calendar including holidays and early closes, a database lock so a job runs once across
restarts and replicas, freshness metadata per source, stale flags, and last-good reads during a
provider outage. Refresh is throttled to once per 30 s.

**Dashboard (P4–P5, UI-01 to UI-12).** Eight signal tiles with sign-aware emphasis, cluster-buy and
10b5-1 flags, quote-source chips and a 10b5-1 exclusion toggle; the insider tape with filters and
dimmed non-open-market rows; the Recharts price chart with value-scaled buy/sell markers; the 13F
holders table with report period; the freshness bar and stale badges; alerts history; the watchlist
editor; new-filing toasts; and the mandatory "not investment advice" disclaimer. SSE quote ticks
fall back to 15 s polling, and the layout is verified at 360, 768 and 1440 px.

**Hardening (P6, AC-01 to AC-10).** EDGAR reconciliation over 40 frozen filings, the NFR-01 load
test, provider-failure injection for fallback and full-outage paths, WCAG 2.1 AA automated scans,
and the production deployment stack (see §5).

## 2. Acceptance evidence

| ID | Criterion | How it is verified in this release |
| --- | --- | --- |
| AC-01 | Parsed fields equal EDGAR on 40 sampled filings | `backend/scripts/reconcile_edgar.py` re-parses `backend/tests/fixtures/reconciliation/documents/` (5 filings × 8 tickers), persists mismatches and exits non-zero on any difference; the browser suite runs an EDGAR reconciliation and shows the result in the Data quality panel |
| AC-02 | A new Form 4 appears in the tape and updates signals within 10 min | `backend/scripts/e2e_new_filing.py` injects a filing into the seeded feed; Playwright asserts the new-filing toast and the refreshed tape |
| AC-03 | Disabling the primary quote provider keeps quotes flowing and shows the source | `backend/scripts/e2e_failure_drill.py --mode fallback` disables the provider through `disabled_providers`, runs a real ingest cycle, and the browser asserts each tile's `finnhub` source chip and price |
| AC-04 | All providers down shows last-good data with a stale badge and no error page | `--mode outage` fails every provider, keeps the stored prices, ages them past the freshness window; the browser asserts the stale badge, last-good price and no alert/error state. The accessibility suite scans this state |
| AC-05 | Load test meets NFR-01 | `backend/scripts/load_test.py` drives 50 concurrent clients with 1 s think time; the suite asserts p95 ≤ 300 ms and zero request errors, and repeats the check from a real browser |
| AC-06 | Visual parity review at 360, 768 and 1440 px | **Open (manual).** The build is automated-tested for responsive behaviour, no horizontal overflow and screenshot capture at all three widths, but parity against the example remains a human review — see §6 |
| AC-07 | Automated accessibility scan reports zero serious violations | `frontend/e2e/a11y.spec.ts` runs axe-core with WCAG 2.1 A/AA tags on the populated dashboard, open panels, loading skeleton, empty watchlist and a genuine stale-outage state; no rule is disabled and no element excluded. `frontend/e2e/keyboard.spec.ts` proves keyboard operation and visible focus |
| AC-08 | Net arithmetic, exclusions, starring and sign tint | Backend unit suites for classification and signals, plus dashboard tests asserting `data-net`, net delta, star counts and the `text-buy`/`text-sell` classes |
| AC-09 | One deduplicated alert per trigger, channels deliver, failures do not fail ingestion | Alert unit tests and the alert-history browser test; delivery failures are recorded without failing the ingest run |
| AC-10 | Bulk loaders are idempotent; the daily cross-check persists only >1% differences | Bulk-loader unit tests, the cross-check job and the Data quality panel test covering the SEC 13F backfill and insider discrepancies |

## 3. Verification run for this release

Run cold on the release commit:

| Check | Result |
| --- | --- |
| `uv run ruff check .` | clean |
| `uv run ruff format --check .` | clean (79 files) |
| `uv run mypy app` | clean (51 source files) |
| `uv run pytest -q` | **98 passed** |
| Alembic `upgrade head → downgrade base → upgrade head` on a scratch database | clean, no new revision |
| `pnpm typecheck` (`tsc --noEmit`) | clean |
| `pnpm lint` (`eslint --max-warnings 0`) | clean |
| `pnpm test -- --run` (Vitest) | **50 passed** across 14 files |
| `pnpm build` (`vite build`) | built |
| `pnpm e2e` (Playwright) | **21 passed** — 5 axe states, 14 dashboard/AC tests including AC-01 to AC-05 and the failure drill, 2 keyboard tests |
| `pnpm smoke:deploy` | **1 passed** — production bundle, migrations from empty, health, hashed assets, SPA fallback, dashboard, axe |

The production smoke suite starts the backend with `ENVIRONMENT=production` after
`alembic upgrade head` on an empty database, seeds fixtures through the real ingest path, serves the
built bundle with the same proxy paths as `ops/nginx.conf`, and checks `/healthz`, `/readyz`, the
dashboard API, content types, deep-link fallback, the rendered dashboard and the accessibility scan.

## 4. Deployment

The stack is `ops/docker-compose.yml` (`api`, `web`, `db`); the full procedure, backups and
rollback are in [`RUNBOOK.md`](RUNBOOK.md).

```bash
cp ops/.env.example ops/.env     # SEC_USER_AGENT, ADMIN_TOKEN, POSTGRES_PASSWORD, WEB_ORIGIN
docker compose -f ops/docker-compose.yml up -d --build
curl -fsS http://localhost:3000/healthz   # {"status":"ok"}
curl -fsS http://localhost:3000/readyz    # {"status":"ready"}
```

The API image applies `alembic upgrade head` before uvicorn starts, `web` waits for the API's
`/readyz` check, and nginx serves the hashed bundle with SPA fallback while proxying `/api`,
`/healthz`, `/readyz` and `/metrics`. With `ENVIRONMENT=production` the API refuses to start if
`SEC_USER_AGENT` has no contact email, `ADMIN_TOKEN` is empty, or `CORS_ORIGINS` contains `*`.

## 5. Upgrade notes

This is the first tagged release; there is no earlier released version to migrate from. For a
pre-release development snapshot:

- Apply the single Alembic chain with `alembic upgrade head` (the container entrypoint does this
  automatically). Back up the database first; see RUNBOOK §3–5.
- `SMM_CONFIG_FILE` was documented but never read by pydantic-settings; it is now `CONFIG_FILE`.
  Update any deployment that relied on the old name (the container sets it explicitly).
- `ENVIRONMENT=production` adds start-up validation. Values that used to boot silently now fail
  fast, which is intentional.
- `DISABLED_PROVIDERS` is available for failure drills and provider maintenance; it is removed from
  every chain, not only quotes.
- The API response shapes are unchanged from the SRS §7.2 contract.

## 6. Known limitations and open items

- **Hosted deployment is still a user step.** The repository ships a working Compose stack, but no
  hosted environment was created here. It needs a host decision (a Docker host/VPS or a managed
  container platform), that host's credentials and a domain, and real `SEC_USER_AGENT`,
  `ADMIN_TOKEN` and `POSTGRES_PASSWORD` values.
- **Container images were not built in this environment.** No Docker, Podman, Postgres or nginx is
  installed on the development machine, so `docker build` and `docker compose up` were not
  executed. The deployed shape was verified with the built bundle, the production entrypoint's
  migration step, a production-configured backend and identical proxy paths; CI now builds both
  images and validates the Compose file.
- **AC-06 visual parity remains a manual review.** Responsive layout, overflow and screenshots are
  automated, but comparing the dashboard against the example is a human judgement.
- **The multi-day soak run has not been completed.** The scheduler, DB lock and job cadences are
  covered by tests, but the plan's unattended run from M3 to release was not executed here.
- **yfinance is unofficial and may break.** It is pinned and isolated behind adapters; EDGAR and
  Alpaca remain the primary sources.
- **UI-14 (TradingView technical chart) is descoped for 1.0** per ADR-003; the Recharts chart (UI-06)
  is the authoritative marker geometry.
- **Provider free-tier limits** (Alpaca, Finnhub, SEC fair access) must be re-verified against the
  configured caps before opening the dashboard to more users.

## 7. Versioning and tag convention

The plan asked for "release notes, v1.0 tag" without fixing the mechanics, so this release records
the least-surprising convention:

- Notes live in `docs/RELEASE_NOTES.md`, one section per minor release, linked from the README.
- Release tags are annotated and named `v<major>.<minor>` (`v1.0`), pointing at the verified commit
  on `main`; patch releases would be `v1.0.1`.
- The version in `backend/pyproject.toml`, `frontend/package.json` and the FastAPI app moves with
  the tag (`1.0.0` here).
