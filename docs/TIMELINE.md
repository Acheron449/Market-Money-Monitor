# Smart Money Monitor — Project Timeline

Version 0.1 (draft) · 8 November 2026 · Companion to the Software Requirements Specification (requirement IDs below refer to it)

## 1. Planning assumptions

- One full-time developer working with AI coding agents (see AGENTS.md), about 46 working days of effort net of holidays. A second developer would compress the plan to roughly seven weeks.
- Start Monday 9 November 2026; v1.0 release Friday 15 January 2027 (ten weeks, including holiday slack).
- Scope is the SRS ‘Must’ requirements plus as many ‘Should’ items as fit; the cut line is in §6.
- Alpaca and Finnhub keys, an SEC User-Agent contact email and a deployment target are available by end of Week 1 (deployment target by Week 8 at the latest).
- US market holidays affect testing and working days: Thanksgiving Thu 26 Nov (market closed, early close Fri 27 Nov), Christmas Fri 25 Dec, New Year Fri 1 Jan. They are also useful test cases for the market-calendar logic.

## 2. Phase overview

| Phase | Name | Dates | Dev-days | Main outcome |
| --- | --- | --- | --- | --- |
| P0 | Foundations and spikes | 9–13 Nov | 4 | Repo, CI, verified provider limits, real Form 4 fixtures, first ADRs |
| P1 | Data layer and Form 4 pipeline | 16–27 Nov | 9 | EDGAR ingestion and parser reproduce real filings for all eight tickers |
| P2 | Quotes, prices, holders, signals, API | 30 Nov–4 Dec | 5 | Contract-complete API; the example front-end renders live data |
| P3 | Scheduler and auto-update | 7–11 Dec | 5 | Jobs run unattended with fallbacks, freshness and stale flags |
| P4 | Front-end integration and polish | 14–24 Dec | 9 (+2 conditional) | Feature-complete dashboard at visual parity, accessible and responsive |
| P5 | Should-have features | 28 Dec–5 Jan | 6 | Streaming, watchlist editor, cluster and 10b5-1 flags, alerts, SEC 13F |
| P6 | Hardening, QA and release | 6–15 Jan | 8 | Reconciliation, load and failure tests, security review, deploy, v1.0 |

## 3. Gantt view

| Workstream | W1 9 Nov | W2 16 Nov | W3 23 Nov | W4 30 Nov | W5 7 Dec | W6 14 Dec | W7 21 Dec | W8 28 Dec | W9 4 Jan | W10 11 Jan |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P0 Foundations | ■ | · | · | · | · | · | · | · | · | · |
| P1 Data layer, Form 4 | · | ■ | ■ | · | · | · | · | · | · | · |
| P2 Quotes, holders, signals, API | · | · | · | ■ | · | · | · | · | · | · |
| P3 Scheduler, auto-update | · | · | · | · | ■ | · | · | · | · | · |
| P4 Front-end | · | · | · | · | · | ■ | ■ | · | · | · |
| P5 Should-haves | · | · | · | · | · | · | · | ■ | ■ | · |
| P6 Hardening, release | · | · | · | · | · | · | · | · | ■ | ■ |
| Soak test (unattended run) | · | · | · | · | · | ■ | ■ | ■ | ■ | ■ |
| Docs and ADRs (continuous) | ■ | ■ | ■ | ■ | ■ | ■ | ■ | ■ | ■ | ■ |

## 4. Milestones

| ID | Date | Milestone | Evidence |
| --- | --- | --- | --- |
| M0 | Fri 13 Nov | Foundations complete | CI green, spike report, keys working, ADR-001 (provider order) and ADR-002 (storage) merged |
| M1 | Fri 27 Nov | Form 4 pipeline matches EDGAR | Parsed rows for all eight tickers equal EDGAR on 40 sampled filings (draft AC-01) |
| M2 | Fri 4 Dec | Internal alpha | API matches the contract in SRS §7; example front-end shows live signals, tape, chart and holders |
| M3 | Fri 11 Dec | Unattended auto-update | Scheduler has run five days unattended; AC-03 passes in a manual drill; soak test starts |
| M4 | Thu 24 Dec | Beta | All UI Must items done; visual parity review and accessibility scan pass |
| M5 | Tue 5 Jan | Should-haves decided | Each Should item is either done or formally cut |
| M6 | Fri 15 Jan | v1.0 release | AC-01 to AC-08 pass; deployed; runbook and release notes published |

## 5. Work breakdown

### P0 Foundations and spikes (4 days)

- Repository, folder layout, uv and pnpm tooling, ruff, mypy, pytest, eslint, GitHub Actions, Docker Compose skeleton.
- Verify Alpaca and Finnhub plan limits and which endpoints are premium; confirm which fields yfinance returns for insider transactions and institutional holders.
- Confirm EDGAR access with a declared User-Agent; build the ticker-to-CIK resolver.
- Run the TradingView licence gate (public implementation, visible attribution, private library access) and record the outcome as ADR-003, with a stub-datafeed widget spike: 0.5 + 0.5 day inside P0’s four days.
- Collect 40 real Form 4 XML fixtures, including joint filers, 10b5-1 sales, amendments and derivative-only filings.
- **Exit:** M0. Provider chain decided and recorded in ADRs.

### P1 Data layer and Form 4 pipeline (9 days)

- Schema and Alembic migrations for the entities in SRS §6.1.
- EDGAR client with rate limiter, retries and caching; filing detection per CIK.
- Form 4 parser tested against the fixtures; code mapping, role normalisation, value and starred logic (SIG-01 to SIG-04).
- Idempotent upserts and amendment handling; six-month backfill for the eight tickers; Finnhub and yfinance insider adapters as fallbacks; ingest\_run logging (ING-01 to 04, 08 to 10).
- **Exit:** M1. The Thanksgiving week is a four-day week and doubles as slack for parser edge cases.

### P2 Quotes, prices, holders, signals and API (5 days)

- Alpaca, Finnhub and yfinance quote and bar adapters; six-month bar backfill; yfinance holders ingest (ING-05 to 07).
- Signal engine (SIG-05 to SIG-08) with unit tests for every rule.
- FastAPI endpoints and Pydantic models for /api/dashboard, /api/history, /api/holders and /api/refresh; contract tests against the shapes in SRS §7.2.
- Point the example front-end at the API without modification as a compatibility check.
- **Exit:** M2.

### P3 Scheduler and auto-update (5 days)

- APScheduler jobs on the cadences in SRS §5.4; NYSE calendar including holidays and early closes; DB lock for single-run jobs; start-up gap-fill (AUT-01, AUT-06).
- Circuit breakers, fallback chains, freshness metadata and stale flags (AUT-05, UI-11 back-end side).
- Throttled refresh endpoint (AUT-04); structured logs and metrics (NFR-09).
- **Exit:** M3. Soak test begins and runs to release.

### P4 Front-end integration and polish (9 days, +2 conditional)

- Port the example UI into the TypeScript project using the design tokens in SRS Appendix A.
- TanStack Query refetch intervals, hidden-tab pause, freshness bar and stale badge (AUT-02, UI-11).
- Sign-aware tile emphasis (SIG-07); tape filters, dimmed non-open-market rows, chart markers, holders table, skeleton and error states (UI-01 to UI-10).
- [Conditional on the TradingView licence gate] UI-14 technical chart: `TvChartPanel` and `tvDatafeed` against the Datafeed API, bar marks per the TradingView implementation plan, lazy-loaded and themed from Appendix A; +2 days from the §6 contingency.
- Responsive checks at 360, 768 and 1440 px; keyboard and screen-reader pass; visual parity review against the example.
- **Exit:** M4.

### P5 Should-have features (6 days)

- SSE quote stream with polling fallback (AUT-03) and new-filing toast (AUT-07).
- Watchlist API and editor (UI-12); cluster-buy flag and 10b5-1 flag with toggle (SIG-09, SIG-10).
- Alerts to email, Telegram or webhook (ADM-03).
- SEC 13F data-set ingestion and insider cross-check job (ING-11, ING-12).
- **Exit:** M5. Anything unfinished is cut or moved to v1.1 by agreement.

### P6 Hardening, QA and release (8 days)

- Reconciliation against EDGAR (AC-01), load test (AC-05), failure injection (AC-03, AC-04), accessibility scan (AC-07).
- Security review: secrets handling, CORS, admin token, dependency scan (NFR-06); provider terms review (SRS §9).
- Production Docker image, deployment, backups, runbook, README, release notes, v1.0 tag.
- **Exit:** M6.

## 6. Cut line and contingency

If the schedule slips, cut in this order and never cut a Must: (0) the optional TradingView technical chart panel (UI-14), (1) alerts, (2) watchlist editor, keeping the watchlist in the YAML config, (3) cluster-buy and 10b5-1 flags, (4) SEC bulk-data loaders, (5) SSE streaming, keeping 15-second polling.

If the TradingView licence gate fails, UI-14 is built on Lightweight Charts (Apache 2.0) or dropped; no Must requirement depends on it.

The largest schedule risk is Form 4 parsing edge cases, which is why P1 has the most days and the fixtures are collected in P0. If yfinance is blocked or changes, the EDGAR and Alpaca paths still deliver every Must except the 13F holders table, which falls back to the SEC data sets and moves up from P5.

## 7. Working rhythm

- Small pull requests with CI required; each PR names the requirement IDs it satisfies.
- Friday demo and a 30-minute reconciliation of ten random filings against EDGAR from Week 2 onward.
- Weekly check of provider limits and terms against configuration.
- Phase exit gates are binary: the milestone evidence above exists, or the phase is not complete.
