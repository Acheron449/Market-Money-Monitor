# ADR-003: TradingView chart library decision

- Status: accepted
- Date: 9 November 2026
- Requirements: UI-06, UI-14, SRS Appendix B #5
- Plan: `docs/TRADINGVIEW.md`

## Gate outcome

| Gate | Result | Evidence |
| --- | --- | --- |
| G1 public service, not personal/internal | **Fail** | This is a self-hosted, personal dashboard; there is no public deployment. |
| G2 no paywall | Pass | Nothing is sold. |
| G3 visible attribution | Not assessed | Only relevant once the library is used. |
| G4 never committed to a public repository | **Fail** | `Acheron449/Market-Money-Monitor` is a public GitHub repository. |
| G5 signed Free Advanced Charts Agreement + private repo access | Not requested | No agreement signed, no repository access. |

The free Advanced Charts licence covers **public, non-paywalled** implementations only. A personal
dashboard in a public repository fails G1 and G4, and no engineering work changes that.

## Decision

- **UI-14 is descoped for v1.0.** No Advanced Charts dependency, no `charting_library` copy step, no
  `CHARTING_LIBRARY_TOKEN` in CI.
- **UI-06 stays on Recharts** and remains the authoritative marker-geometry implementation.
- No vendored or unlicensed copies of the library are committed.

## If the situation changes

If the dashboard is ever deployed publicly without a paywall, re-run the gate. With G1–G5 passing,
follow `docs/TRADINGVIEW.md` as written. With G1/G2 failing, UI-14 may be built on **Lightweight
Charts** (Apache 2.0), which has no redistribution restriction; that is a new ADR, not a reuse of this
one. A reviewer must not sign off UI-06 by looking at a TradingView panel in either case.
