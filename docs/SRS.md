# Smart Money Monitor — Software Requirements Specification

Version 0.1 (draft) · 8 November 2026 · Derived from the attached Perplexity “Smart Money Monitor” example build

## 1. Introduction

### 1.1 Purpose

This document specifies Smart Money Monitor: a web dashboard that tracks insider (SEC Form 4) transactions and institutional (13F) ownership for a watchlist of US equities, converts them into dollar-weighted signals, and keeps itself current from Python libraries (yfinance), public sources (SEC EDGAR) and APIs (Alpaca, Finnhub). It reproduces the look, data model and behaviour of the example and replaces its static data with a live, scheduled data pipeline.

### 1.2 Scope

**In scope (v1.0):** a watchlist of eight default tickers (NVDA, AAPL, TSLA, AMZN, META, AMD, PLTR, COIN), editable; ingestion, normalisation and storage of quotes, daily prices, Form 4 transactions and 13F holders; a signal engine; a REST API; a React dashboard; a scheduler with freshness reporting.

**Out of scope:** order execution (no Alpaca trading endpoints), personalised advice, options-flow / dark-pool / short-interest data, non-US markets, native mobile apps, user accounts and multi-tenancy (post-v1).

### 1.3 Definitions

| Term | Meaning |
| --- | --- |
| Form 4 | SEC filing by insiders (officers, directors, 10% owners) reporting a change in beneficial ownership; due within two business days of the transaction |
| 13F | Quarterly holdings report from institutional managers above $100M in qualifying securities; due 45 days after quarter end |
| Open-market transaction | Form 4 transaction code P (purchase) or S (sale); the only rows that count toward signals |
| Net signal | Open-market buy value minus sell value for a ticker over the lookback window |
| Starred | An open-market buy by a CEO or CFO |
| Tape | Chronological table of insider transactions for the selected ticker |
| Provider | Any external data source: library, API or public website |
| Stale | Data older than twice its scheduled refresh interval |

## 2. Overall description

### 2.1 Product perspective

The attached example is a compiled front-end bundle (React, Tailwind, Recharts, TanStack Query) that calls four endpoints: GET /api/dashboard, GET /api/history/{ticker}, GET /api/holders/{ticker} and POST /api/refresh. The back-end source is not in the archive, so the contract in §7 is inferred from the bundle. This project delivers the missing back-end and live pipeline and keeps the UI contract-compatible so the example front-end can be reused.

### 2.2 User classes

| Class | Needs |
| --- | --- |
| Retail investor / analyst (primary) | Scan eight-plus names quickly, see who is buying or selling and how much, drill into one ticker |
| Self-hosting operator / developer | Configure keys and watchlist, see provider health, trust the numbers |

### 2.3 Operating environment

Python 3.12 back-end in a Linux container; SQLite or PostgreSQL; evergreen desktop and mobile browsers (last two versions of Chrome, Safari, Firefox, Edge) from 360 px viewport width.

### 2.4 Assumptions and dependencies

- SEC EDGAR is the authoritative source for insider data. It requires a descriptive User-Agent with contact details and enforces a fair-access limit of 10 requests per second.
- Free-tier limits for Alpaca and Finnhub, and the unofficial Yahoo endpoints behind yfinance, change without notice. Each shall be re-verified in Phase 0.
- TradingView has no official public data API. It is used for presentation only and is never scraped.
- TradingView Advanced Charts (the Charting Library) is proprietary: access is request-only, its files may not be redistributed or published in a public repository, and the free licence covers public, non-paywalled implementations that keep the TradingView logo visible — not personal or internal use. Lightweight Charts is Apache 2.0 and has no such restriction. The licence gate and conditional design are in the TradingView implementation plan.
- The watchlist is small (50 tickers or fewer). Scaling beyond that is a non-goal for v1.

## 3. System overview

Data flows one way: **Providers → Ingestion jobs → Parsers and normalisers → Store → Signal engine → REST/SSE API → React dashboard.** A scheduler drives the jobs, and every row carries its source and timestamps so the UI can show freshness.

| Layer | Choice | Why |
| --- | --- | --- |
| API | Python 3.12, FastAPI, Pydantic v2 | Typed contracts and OpenAPI for free |
| Jobs | APScheduler in-process with a DB lock | Enough for tens of tickers; Celery or Arq only if scale demands |
| Storage | SQLite (WAL) for dev and single node, PostgreSQL for deployment; SQLAlchemy 2 + Alembic | Zero-setup start, clean upgrade path |
| HTTP | httpx with retry, backoff and per-provider rate limiters | Uniform resilience |
| Frontend | React, Vite, TypeScript, Tailwind, shadcn/ui, TanStack Query, Recharts | Matches the example, reuses its design tokens |
| Live updates | Server-Sent Events for quote ticks, polling for everything else | One-way, simpler than WebSockets |
| Packaging | Docker Compose (api, web, db) | One-command run |
| Observability | JSON logs, /healthz, /readyz, /metrics | Operability |

## 4. Data sources and provider strategy

The API never calls a provider in the request path. Providers feed the store on a schedule; the API reads the store.

| Data need | Primary | Fallbacks | Notes |
| --- | --- | --- | --- |
| Form 4 insider transactions | SEC EDGAR (submissions JSON, filing XML) | Finnhub insider transactions; yfinance insider\_transactions | EDGAR is authoritative and carries owner role and the 10b5-1 flag. Fallbacks have thinner fields and are used for cross-checks and outages |
| Quotes (price, day change %) | Alpaca market data (IEX feed on free plans) | Finnhub quote; yfinance fast\_info | Mark quotes delayed when the plan is not real-time |
| Daily bars (6 months) | Alpaca bars | yfinance history | Split-adjusted close |
| Institutional holders (13F) | yfinance institutional\_holders (MVP) | SEC Form 13F data sets (v1.1); Finnhub ownership if the plan allows | Always show the report period |
| Ticker → CIK, company name | SEC company\_tickers.json | Finnhub profile | Refreshed weekly |
| Market calendar | exchange\_calendars | Alpaca calendar | NYSE holidays and early closes |
| Chart presentation (primary) | Recharts (as in example) | — | Satisfies UI-06, including marker geometry |
| Chart presentation (optional technical chart) | TradingView Advanced Charts, if the licence gate in the TradingView implementation plan passes | TradingView Lightweight Charts (Apache 2.0) | Presentation only, never a data feed; reads our store through the read API |

**Provider caveats.** yfinance is an unofficial scraper of Yahoo endpoints: fine for prototyping and personal use, but review Yahoo’s terms before any public deployment and never make it the only source for a data type. Finnhub and Alpaca plan limits (rate limits, real-time vs delayed, premium-only endpoints) must be confirmed in Phase 0 and kept in configuration, not code.

## 5. Functional requirements

Priority: **M** = must (v1.0), **S** = should (v1.x), **C** = could.

### 5.1 Ingestion (ING)

| ID | Requirement | Pri |
| --- | --- | --- |
| ING-01 | Providers shall sit behind interfaces (QuoteProvider, BarProvider, InsiderProvider, HolderProvider); no provider SDK is imported outside the providers package | M |
| ING-02 | The system shall detect new Form 4 and 4/A filings per watchlist CIK from EDGAR submissions data and fetch the filing XML | M |
| ING-03 | The parser shall extract every non-derivative transaction line: reporting owner, relationship flags, officer title, transaction date, code, acquired/disposed flag, shares, price, shares owned after, 10b5-1 indicator, accession number, filing date | M |
| ING-04 | Inserts shall be idempotent on (accession\_no, line\_no); an amendment supersedes its original | M |
| ING-05 | Quotes (last price, day change %) shall be fetched for all active tickers on the cadence in §5.4 | M |
| ING-06 | First run shall backfill 6 months (configurable) of daily closes; every start-up shall gap-fill missing days | M |
| ING-07 | Top institutional holders per ticker (rank, institution, shares, value, QoQ change %) shall be stored with their report period | M |
| ING-08 | Each data type shall use an ordered fallback chain; on error, timeout or empty result the next provider is tried and the producing provider is recorded on each row | M |
| ING-09 | Each provider shall have a rate limiter and circuit breaker (open after 5 consecutive failures, half-open after 5 minutes) | M |
| ING-10 | Every job run shall be logged (job, provider, start, end, status, rows, error) | M |
| ING-11 | A daily job shall cross-check insider rows against a second provider and log discrepancies above 1% in shares or value | S |
| ING-12 | SEC bulk data sets (Insider Transactions, Form 13F) shall be loadable for historical backfill | S |
| ING-13 | A CLI shall allow manual runs, e.g. smm ingest --job form4 --ticker NVDA --since 2026-05-01 | C |

### 5.2 Classification and signals (SIG)

| ID | Requirement | Pri |
| --- | --- | --- |
| SIG-01 | Transaction codes shall map to action and label per §6.2 | M |
| SIG-02 | value = shares × price per share; null when no price is reported (grants, gifts, withholdings) | M |
| SIG-03 | Officer titles shall normalise to CEO, CFO, COO, CTO, President, Director, 10% Owner or Other | M |
| SIG-04 | A row is starred when action is buy and role is CEO or CFO | M |
| SIG-05 | Per ticker over the lookback window: netValue = Σ buy value − Σ sell value; txnCount = number of buy and sell rows; starredCount = number of starred rows. Only open-market (P, S) rows count; all other rows are displayed but excluded | M |
| SIG-06 | Lookback defaults to 6 months and is configurable from 1 to 24 months by config and query parameter | M |
| SIG-07 | Tile emphasis shall be sign-aware: | net |
| SIG-08 | Signals shall be recomputed after every insider ingest, in under 1 s for 50 tickers | M |
| SIG-09 | Flag a cluster buy when three or more distinct insiders make open-market buys within 14 days | S |
| SIG-10 | Flag sales made under a Rule 10b5-1 plan; show a badge and offer a toggle to exclude them from net (included by default) | S |
| SIG-11 | A drill-down shall list the exact rows that make up a ticker’s net signal | C |

### 5.3 Dashboard UI (UI)

| ID | Requirement | Pri |
| --- | --- | --- |
| UI-01 | Header: logo mark, title “Smart Money Monitor”, small-caps subtitle “insiders & institutions”, latest filing as relative days, Refresh button that spins while pending | M |
| UI-02 | Signal tiles (2 / 4 / 8 columns by breakpoint), one per ticker: symbol, day change %, signed compact net value, “N txns · net”, ★ count and a cluster-buy badge when SIG-09 applies. Click selects the ticker; the selected tile has a champagne ring | M |
| UI-03 | Insider tape for the selected ticker with columns Date, Insider (name, role badge, ★), Type badge, Shares, Value; sticky header; scrolls inside its panel | M |
| UI-04 | Tape filters: All, Buys only, C-suite (CEO or CFO); empty-state message when nothing matches | M |
| UI-05 | Non-open-market rows render dimmed (45% opacity); the tape caption explains the exclusion and the ★ meaning | M |
| UI-06 | Price and insider activity chart: 6-month close line; ▲ buy and ▼ sell markers on trade dates; marker radius = 5 + 9 × √(value ÷ max value in window) px; one marker per date (the largest wins); tooltip with date and close; empty states for no history and no trades; this chart is the authoritative marker geometry, which UI-14 can only approximate | M |
| UI-07 | Holders table: #, Institution, Shares, Value, QoQ % (shown as — when null); skeleton rows while loading; empty state | M |
| UI-08 | Loading skeletons for tiles and panels; full-page error state with Retry | M |
| UI-09 | Footer disclaimer: Form 4 lag of up to two business days, 13F quarterly delay, lookback window, data refreshed time, “For information only — not investment advice” | M |
| UI-10 | Dark theme with the tokens in Appendix A; Cormorant Garamond for display, Inter for UI, tabular numerals for all figures | M |
| UI-11 | Per-source freshness indicator (“Quotes 12 s ago · Filings 4 min ago”) and a stale badge when a source exceeds twice its cadence | M |
| UI-12 | Watchlist editor (add or remove tickers, reorder) | S |
| UI-13 | Light theme and a CSV export of the visible tape | C |
| UI-14 | Optional technical chart panel using TradingView Advanced Charts, fed only from the store through the Datafeed API and enabled only when the licence gate in the TradingView implementation plan passes, with TradingView attribution visible | C |

### 5.4 Auto-update (AUT)

| ID | Requirement | Pri |
| --- | --- | --- |
| AUT-01 | A scheduler shall run the jobs below; market-hours logic uses the NYSE calendar in America/New\_York, including holidays and early closes | M |
| AUT-02 | The front-end shall refetch the dashboard every 60 s, and the open ticker’s history and holders every 5 min, and shall pause while the tab is hidden | M |
| AUT-03 | Quote ticks shall stream over SSE during market hours, falling back to 15 s polling if the stream drops | S |
| AUT-04 | Manual refresh (POST /api/refresh) shall enqueue an immediate run, return 202, and be throttled to one per 30 s | M |
| AUT-05 | When a provider fails, the last good data shall continue to be served with a stale flag; the UI shall never show a blank page because a provider is down | M |
| AUT-06 | Jobs shall be single-run across restarts and replicas (DB lock) and safe to re-run | M |
| AUT-07 | When a new Form 4 arrives, the UI shall show a toast naming ticker, insider, action and value | S |

| Job | Market hours (09:30–16:00 ET) | Off-hours |
| --- | --- | --- |
| Quotes | every 15–30 s | every 15 min on trading days, none on weekends |
| Form 4 poll | every 5 min | every 5 min until 22:00 ET on weekdays, hourly otherwise |
| Daily bars | gap-fill at start-up | 16:30 ET each trading day |
| 13F holders | daily check, hourly during the weeks around each quarterly filing deadline | same |
| Signals | event-driven after insider ingest | same |
| Ticker/CIK map | weekly | weekly |
| Provider health ping | every minute | every 5 min |

### 5.5 Alerts and administration (ADM)

| ID | Requirement | Pri |
| --- | --- | --- |
| ADM-01 | Configuration by environment variables and a YAML file (watchlist, lookback, cadences, provider order); a .env.example documents every key | M |
| ADM-02 | Admin endpoints (watchlist, refresh from non-local hosts) require a bearer token | M |
| ADM-03 | Alerts by email, Telegram or webhook for: CEO/CFO open-market buy, single transaction above a threshold, net signal crossing ±$10M, cluster buy | S |
| ADM-04 | A provider-health page shows breaker state, last success, error rate | C |

## 6. Data requirements

### 6.1 Entities

| Entity | Key fields |
| --- | --- |
| ticker | symbol (PK), cik, name, exchange, active, sort\_order |
| quote | symbol (PK), price, change\_pct, as\_of, source, delayed |
| price\_bar | (symbol, date) PK; open, high, low, close, volume, source |
| insider\_txn | (accession\_no, line\_no) PK; symbol, filing\_date, txn\_date, insider\_name, insider\_cik, officer\_title, role, txn\_code, action, shares, price, value, shares\_after, is\_10b5\_1, is\_amendment, source |
| holder | (symbol, report\_period, institution\_cik) PK; institution, shares, value, prev\_shares, qoq\_change\_pct, rank, source |
| signal\_snapshot | (symbol, as\_of, lookback\_months) PK; net\_value, buy\_value, sell\_value, txn\_count, starred\_count |
| ingest\_run | id, job, provider, started\_at, finished\_at, status, rows, error |

Money is handled as Decimal in the back-end and serialised as JSON numbers. All timestamps are stored in UTC; trading dates are in America/New\_York.

### 6.2 Transaction code mapping

| Code | typeLabel | action | Counts toward signals |
| --- | --- | --- | --- |
| P | Open-market buy | buy | Yes |
| S | Open-market sell | sell | Yes |
| A | Award / grant | other | No |
| M, X, C | Option exercise / conversion | other | No |
| F | Tax withholding | other | No |
| G | Gift | other | No |
| D | Disposed to issuer | other | No |
| Any other code | Other | other | No |

### 6.3 Derived values

- **Net signal:** Σ(buy value) − Σ(sell value) over the lookback window, open-market rows only.
- **QoQ %:** (shares now − shares previous quarter) ÷ shares previous quarter × 100; null when there is no prior quarter.
- **Compact currency:** $K, $M, $B, $T with a sign for net values; — for null.

## 7. External interfaces

### 7.1 REST API

Paths match the example so its front-end works unchanged; items marked new are additions.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | /api/dashboard | Signals, quotes, tape, lookbackMonths, latestFilingDate, generatedAt and freshness (new); optional `exclude10b5_1=true` for SIG-10 |
| GET | /api/history/{ticker} | Daily closes, default range 6 months |
| GET | /api/holders/{ticker} | Top holders, default limit 10 |
| POST | /api/refresh | Trigger an immediate refresh; 202 with job id; throttled |
| GET | /api/stream | SSE quote ticks with 20 s heartbeat (new) |
| GET, PUT | /api/watchlist | Read or replace the watchlist; validates ticker and resolves CIK; admin (new) |
| GET | /healthz, /readyz, /metrics | Liveness, readiness, Prometheus metrics (new) |

### 7.2 Response shapes

```typescript
type Dashboard = { signals: Signal[]; quotes: Record<string, Quote>; tape: Txn[]; lookbackMonths: number; latestFilingDate: string | null; generatedAt: string; freshness: Record<string, { asOf: string; stale: boolean }> }
type Signal = { ticker: string; netValue: number; txnCount: number; starredCount: number; clusterBuy: boolean }
type Quote = { price: number; changePct: number; asOf: string; source: string; delayed: boolean }
type Txn = { key: string; ticker: string; date: string; name: string; role: string | null; action: 'buy' | 'sell' | 'other'; typeLabel: string; shares: number; value: number | null; starred: boolean; is10b5_1?: boolean }
type History = { date: string; close: number }[]
type Holder = { rank: number; institution: string; shares: number; value: number; qoqChangePct: number | null; reportPeriod?: string }
```

### 7.3 Error handling

Errors use a JSON body with code and message. A failed provider never produces a 5xx on read endpoints; the response is served from the store with stale flags.

## 8. Non-functional requirements

| ID | Category | Requirement |
| --- | --- | --- |
| NFR-01 | Performance | Dashboard p95 ≤ 300 ms (warm, 8 tickers, 6 months) at 50 concurrent users |
| NFR-02 | Freshness | New Form 4 visible within 10 min of EDGAR acceptance; quotes no older than 60 s in market hours |
| NFR-03 | Resilience | Any single provider outage causes no user-visible error; all-provider outage shows last-good data with a stale badge |
| NFR-04 | Accuracy | 100% match to EDGAR on golden-file Form 4 fixtures; at least 99% on sampled reconciliation |
| NFR-05 | Rate limits | Stay at or under 50% of any documented provider limit; SEC traffic at or under 5 requests per second |
| NFR-06 | Security | Secrets only in environment or secret store and never sent to the browser; data-only API keys; CORS allow-list; dependency scanning in CI |
| NFR-07 | Accessibility | WCAG 2.1 AA; buy and sell never conveyed by colour alone (▲/▼ and +/− signs); tiles and filters keyboard-operable |
| NFR-08 | Maintainability | Type hints, ruff and mypy clean, at least 85% test coverage on parsers and signals, ADRs for provider decisions |
| NFR-09 | Observability | Structured logs, per-job metrics, provider error rates, alert on job failure |
| NFR-10 | Portability | docker compose up yields a working system with only API keys supplied |

## 9. Compliance and legal

- Follow the SEC fair-access policy and send a declared User-Agent with contact email on every EDGAR request.
- Review each provider’s terms before launch; honour attribution and redistribution limits. This applies in particular to yfinance (unofficial) and TradingView (presentation only). Advanced Charts is non-redistributable, must not be committed to a public repository, and keeps its attribution visible.
- Insider names come from public filings; no other personal data is collected.
- The disclaimer in UI-09 is mandatory and may not be removed. The product reports disclosed activity; it gives no recommendations.

## 10. Risks

| ID | Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- | --- |
| R1 | yfinance breaks or is rate-limited | High | Medium | Adapter isolation, pinned version, EDGAR primary for insiders, fallback chain |
| R2 | Free-tier limits or endpoints change | Medium | Medium | Verify in Phase 0, keep limits in config |
| R3 | Form 4 edge cases (joint filers, footnotes, derivative tables, amendments) | High | High | Golden fixtures from real filings, daily cross-check job |
| R4 | 13F lag makes QoQ look more current than it is | Medium | Medium | Always show report period |
| R5 | TradingView terms prohibit data scraping | Medium | High | Presentation-only use |
| R6 | Signals misread (10b5-1 sales, tax-driven sales) | Medium | Medium | Flag plans, exclude non-open-market rows, footer disclaimer |
| R7 | Duplicate or missed runs after restart | Medium | Medium | DB lock, idempotent upserts, start-up gap-fill |
| R8 | Read as investment advice | Low | High | Disclaimers, neutral language |

## 11. Verification and acceptance

| ID | Test |
| --- | --- |
| AC-01 | For 5 sampled filings per ticker (40 total), parsed shares, price, code, date and owner equal EDGAR |
| AC-02 | A new Form 4 injected into a test feed appears in the tape and updates signals within 10 min |
| AC-03 | With the primary quote provider disabled, quotes continue from a fallback within one cycle and the UI shows the source |
| AC-04 | With all providers disabled, the UI shows last-good data and a stale badge, with no error page |
| AC-05 | Load test meets NFR-01 |
| AC-06 | Visual parity review against the example at 360, 768 and 1440 px |
| AC-07 | Automated accessibility scan reports zero serious violations |
| AC-08 | Unit tests prove: net = buys − sells; awards, gifts and withholdings excluded; starred only for CEO/CFO buys; tint follows sign |

## Appendix A. Findings from the example build

**Layout.** Header, then eight signal tiles, then a two-pane row (tape 55% and chart 45%, 440 px tall on large screens), then the holders table and disclaimer footer. Routing is hash-based.

**Design tokens (dark).** Background hsl(160 27% 6%), card hsl(157 25% 10%), text hsl(150 16% 91%), border hsl(150 24% 16%), muted text hsl(153 9% 54%), champagne / primary hsl(45 51% 70%), buy hsl(145 63% 49%), sell hsl(6 53% 49%). Fonts: Cormorant Garamond (display, semibold), Inter (UI). Small-caps labels with 0.12em tracking, tabular numerals.

**Behaviour to correct.** The example’s tile border colour is chosen by magnitude only (≥ $10M green, ≥ $1M red), so a large net sale can render green. SIG-07 makes it sign-aware.

**Not recoverable from the archive.** Back-end code, the real data, the lookback value and the number of holder rows. See open questions.

## Appendix B. Open questions

1. Where will this be deployed (self-hosted VPS, Fly, Render, other) and is a paid data plan in budget?
2. Will the watchlist stay near eight names, or grow to hundreds?
3. Should holders rank by shares or by value, and show top 10?
4. Are alerts needed for v1.0 or can they follow in v1.x?
5. Is this for personal use or a public product? That decides the weight of the yfinance terms review and gates UI-14, because the free Advanced Charts licence covers public, non-paywalled implementations only. Answer before M0.
