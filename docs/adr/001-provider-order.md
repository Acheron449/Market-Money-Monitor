# ADR-001: Provider order and fallback chains

- Status: accepted
- Date: 9 November 2026
- Requirements: ING-01, ING-08, ING-09, NFR-03, NFR-05

## Decision

| Data | Primary | Fallbacks |
| --- | --- | --- |
| Form 4 insiders | SEC EDGAR (submissions JSON + filing XML) | Finnhub insider transactions, yfinance `insider_transactions` |
| Quotes | Alpaca snapshots (IEX feed on free plans) | Finnhub `/quote`, yfinance `fast_info` |
| Daily bars | Alpaca daily bars, split-adjusted | yfinance `history` |
| 13F holders | yfinance `institutional_holders` (MVP) | SEC 13F data sets (v1.1) |

Order is configuration (`provider_order` in `smm.yaml`), not code. Providers are built once in
`app/providers/registry.py`, each with its own rate limiter (`RateLimiter`) and circuit breaker
(open after 5 consecutive failures, half-open after 5 minutes). The registry sorts each chain by the
configured order and skips providers with no credentials.

## Rationale

- EDGAR is authoritative, carries the owner role and the 10b5-1 indicator, and filings are immutable,
  so it is always first for insiders. Its 5 req/s ceiling is enforced by the limiter (the SEC allows 10).
- Alpaca has the cleanest free market-data terms and returns split-adjusted daily bars and snapshots
  in one API, so it leads for prices; the feed is configurable because IEX is delayed.
- Finnhub is the cheapest second opinion for quotes and a thin insider fallback.
- yfinance is unofficial and can break without notice, so it is last for prices and insiders, while
  remaining the practical MVP source for 13F holders until the SEC data sets are wired in.

## Consequences

- Read endpoints never fail because a provider is down: last-good rows stay in the store with the
  freshness/stale flags from `app/services/freshness.py`.
- Each stored row records its `source`; `ingest_run` records every attempt with provider, status,
  rows and error.
- Re-verify free-tier limits and terms before launch (SRS §9); limits live in configuration.
