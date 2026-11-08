# Smart Money Monitor — TradingView Implementation Plan

Version 0.1 (draft) · 8 November 2026 · Companion to [SRS](SRS.md) (UI-06, UI-11, UI-14, SIG-05, AUT-02, NFR-06, NFR-07) and the [Timeline](TIMELINE.md) (P0, P4, §6).

The plan targets **TradingView Advanced Charts** (the “Charting Library”), `latest` documentation, v32 or newer. API links below point at that documentation; the pinned version wins where they differ.

**TradingView is presentation only.** It is never a data source, never scraped, and nothing here may call a provider. The panel reads our store through the existing read API, exactly like the rest of the dashboard. The library ships with no market data.

## 1. Licence gate (do this before writing code)

Advanced Charts is **proprietary**, not open source. Access is by request only, the files are **not redistributable**, and the free licence is limited to public, non-paywalled implementations that keep the TradingView attribution visible. It is explicitly **not** licensed for private, personal, internal or behind-a-paywall use. ([Get started](https://www.tradingview.com/charting-library-docs/latest/quick-start), [Introduction](https://www.tradingview.com/charting-library-docs/latest/introduction), [Free Advanced Charts Agreement](https://s3.amazonaws.com/tradingview/charting_library_license_agreement.pdf))

All five gates must pass before integration work starts. They are commercial/licensing gates, not engineering trade-offs.

| # | Gate | Evidence required |
| --- | --- | --- |
| G1 | The implementation is a **public** service, not personal, internal or a demo | Deployment URL reachable without an account, or with free registration only |
| G2 | It is **not** behind a paywall and there is no plan to put the chart behind one | Product/deployment decision recorded in ADR-003 |
| G3 | TradingView attribution and logo stay visible; no branding featureset is disabled | Screenshot of the rendered panel in the review; `adaptive_logo` and logo featuresets left at default |
| G4 | Library files are **never** committed to a public repository | `.gitignore` entry, build-time copy step, CI check that `frontend/public/charting_library/` is untracked |
| G5 | The Free Advanced Charts Agreement is signed and GitHub access to the private repository is granted | Access confirmation from TradingView; `pnpm install` resolves the pinned git dependency |

**Branches.**

| Gate result | Chart library | Consequence |
| --- | --- | --- |
| G1–G5 pass | Advanced Charts, pinned semver | Sections 4–9 apply as written |
| Any gate fails | **Lightweight Charts** (Apache 2.0) — or no technical panel | UI-06 is unaffected; UI-14 is re-scoped to the open-source library or dropped |

Do not partially adopt: a self-hosted personal dashboard with a public repository fails G1 and G4, and no amount of engineering fixes that. Record the decision, the gate evidence and the branch in `adr/003-chart-library.md` before M0.

**Open question this closes:** SRS Appendix B #5 (personal use vs public product). Until it is answered, UI-14 stays unstarted.

## 2. Capability check against the API

| Need | API support | Verdict |
| --- | --- | --- |
| 6-month close line | Line series; `visible_plots_set: 'c'` in `LibrarySymbolInfo` restricts the symbol to close-only, line-based styles | Works |
| ▲/▼ markers on trade dates | Bar marks (`supports_marks` + `getMarks`) are **circles with a one-character label**; triangle drawings exist as `arrow_up`/`arrow_down` shapes | Works with caveats (§3) |
| Marker size by value | `Mark.minSize` only — there is **no radius or size field**; arrow drawings are fixed-size | Approximate only (§3) |
| One marker per date, largest wins | Our datafeed decides which mark to emit per bar time | Works |
| Tooltip with date, close and value | Built-in tooltip renders **plain text only**; custom HTML tooltip components are **Trading Platform only** | Works, plain text |
| No OHLC data needed | `getBars` may return `open = high = low = close = close` | Works |
| Dark theme and fonts | `theme: 'dark'`, `overrides`, `custom_font_family`, `custom_css_url` | Works |
| Freshness display | `data_status: 'endofday'`; UI-11 indicator stays **outside** the iframe | Works |
| Accessibility audit | Chart renders in an iframe; axe cannot inspect inside it | Manual pass (§8) |

References: [LibrarySymbolInfo](https://www.tradingview.com/charting-library-docs/latest/api/interfaces/Charting_Library.LibrarySymbolInfo), [Marks](https://www.tradingview.com/charting-library-docs/latest/ui_elements/Marks), [Mark](https://www.tradingview.com/charting-library-docs/latest/api/interfaces/Charting_Library.Mark), [CreateShapeOptions](https://www.tradingview.com/charting-library-docs/latest/api/interfaces/Charting_Library.CreateShapeOptions).

## 3. Marker geometry caveat (read before quoting UI-06)

UI-06 requires a marker radius of `5 + 9 × √(value ÷ max)` pixels. **Advanced Charts cannot express that requirement exactly.** Bar marks are circles whose size is driven by their label and a `minSize` floor, and arrow drawings have a fixed glyph size.

The agreed mapping for UI-14 is:

1. **Default:** bar marks, one per trading date, labelled `▲` (buy) or `▼` (sell), coloured with the buy/sell tokens, with `labelFontColor` set to the background token for contrast.
2. `minSize = round(5 + 9 × √(value ÷ maxValueInWindow))`, clamped to `[5, 14]` px.
3. The circle may render **larger** than `minSize`; treat the value as a floor, not a radius. Do not scale by drawing shapes.

Consequences, recorded so nobody “fixes” them later:

- The visual encoding is proportional-ish, not exact. Encoding remains redundant: ▲/▼ and the tape carry the same information.
- **UI-06 stays authoritative and stays on Recharts.** The TradingView panel (UI-14) is an additional, optional technical view; it must not be described as satisfying UI-06, and a reviewer must not sign off UI-06 by looking at it.
- If the exact radius matters more than the extra interactions, drop UI-14. That is cheaper than arguing with the library.

Rejected alternative: `chart().createShape({ time, price }, { shape: 'arrow_up' | 'arrow_down', ... })` gives real triangles but fixed size, and every marker becomes a user drawing that must be locked, marked non-selectable, non-saveable and non-undoable. It also litters the objects tree. Not worth it for an optional panel.

## 4. Delivery, versioning and build

The library is not on the public npm registry and must not be redistributed.

- Add it as a pinned git dependency: `"charting_library": "git@github.com:tradingview/charting_library.git#semver:32.0.0"`. No `^`, no `latest`; upgrades are a deliberate PR with a visual diff.
- `postinstall` copies `node_modules/charting_library/charting_library/` to `frontend/public/charting_library/`. That directory is **git-ignored** and never committed.
- `library_path: '/charting_library/'` — same origin as the app, trailing slash. A separate origin would need CORS headers on every file and buys nothing here.
- CI and Docker need read-only access to the private repository. Pass the token as a BuildKit secret (`RUN --mount=type=secret,id=tv_token`), not a build arg that survives in image history. `CHARTING_LIBRARY_TOKEN` is build-time only; it is never a runtime variable and never reaches the browser bundle.
- Lazy-load the widget module with a dynamic `import()` inside the panel’s effect so the ~670 KB library does not enter the initial bundle; verify with `pnpm build` chunk output.
- Keep the licence/notice files that ship with the copies.
- Record `TradingView.version()` in the P0 spike notes and pin that exact version.

If CI cannot be given repository access, stop: the conditional feature is not deliverable, and that is a §6 contingency event, not a reason to vendor the files.

## 5. Widget configuration

Files:

    frontend/src/chart/TvChartPanel.tsx   panel, lifecycle, theming
    frontend/src/chart/tvOptions.ts       widget options builder
    frontend/src/chart/tvDatafeed.ts      Datafeed API implementation
    frontend/src/chart/barTime.ts         one time helper, used by datafeed and marks

Lifecycle rules:

- Create **one** widget per mount. `useEffect` with an empty dependency list (plus a `symbol` change handled by `chart().setSymbol()`), never on every render.
- Wait for `chartReady()`; `onChartReady()` is deprecated. Widget-level `setSymbol()` is also deprecated — use `chart().setSymbol()`.
- Cleanup calls `widget.remove()`. React 18 StrictMode mounts twice in development; the cleanup must be complete or the chart is created twice.
- `autosize: true` with a container that has an explicit height (440 px on large screens, matching the two-pane row), and a `ResizeObserver` fallback if autosize misbehaves in the 45% pane.
- The panel keeps its own error boundary: a failure to load the library must not take down the dashboard (UI-08).

Options:

```ts
{
  container,
  library_path: '/charting_library/',
  datafeed,
  symbol,                       // plain ticker, e.g. 'NVDA' — no colon
  interval: '1D',
  locale: 'en',
  timezone: 'America/New_York',
  theme: 'dark',
  autosize: true,
  debug: false,
  custom_font_family: 'Inter, sans-serif',
  disabled_features: [ /* see below */ ],
  enabled_features: [ /* see below */ ],
  overrides: { /* tokens */ },
}
```

`disabled_features` (minimum verified set; resolve the rest against Featuresets for the pinned version):

- `header_widget` — no symbol search, no header panel.
- `use_localstorage_for_settings`, `save_chart_properties_to_local_storage` — no persisted chart settings across users or sessions; every load renders the same configured chart.
- `context_menus`, `legend_context_menu`, `pane_context_menu`, `scales_context_menu` — no right-click menus that do nothing useful here.
- `border_around_the_chart`, `volume_force_overlay`, `symbol_info`.

`enabled_features`:

- `pin_bar_mark_tooltips_on_click` — marks reveal their tooltip on click, which is also the touch behaviour.
- `accessible_keyboard_shortcuts`, `aria_crosshair_price_description` — the only accessibility featuresets the library offers (the ARIA one is English-only).

**Never disable the TradingView branding featuresets** (`adaptive_logo` and friends). That is licence condition G3.

Theming: derive the override values from the Appendix A tokens at build time rather than hard-coding hex. Minimum keys: `paneProperties.background`, `paneProperties.backgroundType: 'solid'`, `paneProperties.vertGridProperties.color`, `paneProperties.horzGridProperties.color`, `scalesProperties.textColor`, `scalesProperties.lineColor`, `mainSeriesProperties.lineStyle.color`, `mainSeriesProperties.lineStyle.linewidth`. After `chartReady()`, switch the series to a line chart type (confirm the `SeriesType` value against the pinned typings in the P0 spike — do not guess it) so the panel matches UI-06’s close line.

## 6. Datafeed specification

Implements `IBasicDataFeed` — `onReady`, `searchSymbols`, `resolveSymbol`, `getBars`, `subscribeBars`, `unsubscribeBars` — plus `getMarks`. ([Required methods](https://www.tradingview.com/charting-library-docs/latest/connecting_data/datafeed-api/required-methods), [Additional methods](https://www.tradingview.com/charting-library-docs/latest/connecting_data/datafeed-api/additional-methods))

Hard rules:

- **Every callback is asynchronous** (`setTimeout(…, 0)`); synchronous callbacks cause stack overflows inside the library.
- Bar `time` is **milliseconds**; `periodParams.from`/`to`, mark times and server time are **seconds**.
- No provider calls, no direct provider SDK, no Yahoo/Alpaca/Finnhub access. Only `/api/dashboard` and `/api/history/{ticker}`.
- Never mutate the arrays after passing them to a callback; pass copies.

### 6.1 `onReady`

```ts
{
  supports_search: true,          // restricted to the watchlist, not a global directory
  supports_group_request: false,
  supports_marks: true,
  supports_timescale_marks: false,
  supports_time: true,
  exchanges: [{ value: 'NASDAQ', name: 'NASDAQ', desc: 'NASDAQ' }, /* … from the store */],
  symbols_types: [{ name: 'Stock', value: 'stock' }],
  supported_resolutions: ['1D'],
}
```

### 6.2 `resolveSymbol`

One `LibrarySymbolInfo` per watchlist ticker, built from the store’s `ticker` row:

| Field | Value |
| --- | --- |
| `ticker`, `name` | Ticker symbol, e.g. `NVDA` (no exchange prefix) |
| `description` | Company name |
| `type` | `stock` |
| `exchange`, `listed_exchange` | `ticker.exchange` (e.g. `NASDAQ`) |
| `session` | `0930-1600` |
| `timezone` | `America/New_York` |
| `minmov` / `pricescale` / `minmove2` | `1` / `100` / `0` |
| `has_intraday` | `false` |
| `has_daily` | `true` |
| `daily_multipliers` | `['1']` — required to enable daily resolutions |
| `has_weekly_and_monthly` | `false` — let the library aggregate daily bars |
| `supported_resolutions` | `['1D']` |
| `visible_plots_set` | `c` — close-only, line styles |
| `format` | `price` |
| `data_status` | `endofday` |
| `session_holidays` / `corrections` | Optional; not needed for daily bars |

Unknown symbols (anything off the watchlist) call `onResolveErrorCallback('unknown_symbol')`.

### 6.3 `getBars`

Source: `GET /api/history/{ticker}` → `{ date: 'YYYY-MM-DD', close: number }[]`, already split-adjusted and store-backed.

Rules the contract test must enforce:

- Ascending order, `time` in ms via `barTime(date)`.
- Every bar in `[from, to)` is returned, not just `countBack` bars.
- If the range holds fewer bars than `countBack`, prepend earlier bars until `countBack` is met.
- Return at least two bars when they exist; a single bar breaks clicking on the chart.
- Empty result **and** no older data → `onHistoryCallback([], { noData: true })`. An empty result with older data is an error, not `noData`.
- On HTTP failure or timeout → `onErrorCallback('history unavailable')`; never `noData`.
- `open = high = low = close = close`; no volume. `visible_plots_set: 'c'` keeps the UI line-only.
- Short range (six months by default, configurable): the panel requests the lookback window, not the full history.

Sketch:

```ts
const bars = rows.map((r) => ({ time: barTime(r.date), open: r.close, high: r.close, low: r.close, close: r.close }));
const inRange = bars.filter((b) => b.time >= from * 1000 && b.time < to * 1000);
const pad = Math.max(0, countBack - inRange.length);
const firstIdx = inRange.length ? Math.max(0, bars.indexOf(inRange[0]) - pad) : bars.length;
setTimeout(() => onHistoryCallback(bars.slice(firstIdx)), 0);
```

### 6.4 Subscriptions

- No intraday data, so `subscribeBars` registers `subscriberUID` and does nothing else.
- After the 16:30 ET bars job (or a bars SSE event), call `onRealtimeCallback` with the **latest** bar only, and only if its time is greater than or equal to the last loaded bar.
- **Never push a historical bar** — that produces `putToCacheNewBar: time violation`. If history changes, `chart().resetData()` and re-request.
- `unsubscribeBars` removes the listener. The library calls it with a delay; keep pushing until it does.

### 6.5 `getMarks`

Marks carry the insider signal onto the price line.

- Input: the tape from `/api/dashboard` for the selected ticker, **open-market rows only** (`P`, `S`). Non-open-market rows never produce a mark, matching SIG-05.
- Group by trading date and keep the **largest `value`**; null values sort last. One mark per date.
- `time` must equal the time of an existing bar (`barTimeSeconds(date)`); the library rejects marks that do not land on a bar.
- At most 10 marks per bar — structurally impossible here, but assert it in tests.
- `label`: `▲` / `▼`; `color`: buy/sell token; `labelFontColor`: background token; `minSize` per §3.
- `text`: plain text only, multi-line, e.g. `2026-11-04 · J. Smith (CFO)` and `12,000 sh · $1.8M · 10b5-1`. No HTML; the Advanced Charts tooltip does not render it. Show the same details in the tape, which is the accessible and complete view.
- Call `chart().refreshMarks()` after a dashboard refetch that changes the tape, and after a symbol change.

### 6.6 Failure behaviour

- Fewer than two bars, or a 5xx from `/api/history`: `onErrorCallback`, and the panel shows the standard empty/error state (UI-08).
- Stale data still renders: the chart is labelled `endofday`, and the freshness bar outside the iframe (UI-11) is the source of truth.
- Abort in-flight `/api/history` requests on symbol change and unmount.

## 7. Time handling

- One helper, `barTime(date: string): number` returning `Date.UTC(y, m - 1, d)`, used by both `getBars` and `getMarks`. No second implementation, ever.
- `barTimeSeconds()` is `barTime() / 1000` and exists only to feed the mark API.
- Keep bar times at UTC midnight of the **trading date**. The library labels them with the configured `America/New_York` timezone; verify the rendered label in the P0 spike for a date in both EST and EDT, not just one.
- The NYSE calendar already knows holidays and early closes; daily bars only exist on trading days, so no synthetic bars are emitted.
- Tests must include a summer date (EDT), a winter date (EST) and a date either side of the DST change.

## 8. Accessibility, freshness and traceability

- The chart is an iframe. Axe cannot inspect inside it, so AC-07 covers the page, and the chart gets a **manual checklist**: tab order, keyboard scroll/zoom, mark tooltip reachable by keyboard and by tap, focus not trapped, visible focus ring.
- The tape is the equivalent non-visual path; the panel carries a visible caption saying so, plus the selected ticker and the data date.
- Buy/sell is never colour-only: ▲/▼ labels and the tape’s signed values stay (AGENTS.md §5).
- UI-11 freshness and the UI-09 disclaimer stay outside the iframe; the panel does not repeat or weaken the disclaimer.
- Attribution stays visible (G3), including on narrow viewports where the library shows its compact logo.

| Requirement | Where satisfied |
| --- | --- |
| UI-06 | Unchanged, Recharts; §3 states the deviation for UI-14 |
| UI-11 | §8, outside the iframe |
| UI-14 | §1, §4–§7 |
| SIG-05 | §6.5 — open-market rows only |
| AUT-02 | §6.4 — latest bar only after the 16:30 job; no polling inside the chart |
| NFR-06 | §4 — build-time token, no secrets in the bundle |
| NFR-07 / AC-07 | §8 — manual iframe checklist plus the tape |
| SRS §9 | §1 — attribution and no redistribution |

## 9. Testing, effort and risks

Unit tests (offline, no network):

- `barTime` across EST, EDT and both sides of the DST boundary; ms/seconds separation.
- `getBars`: ascending, in-range completeness, `countBack` padding, `noData` vs error, at least two bars.
- `getMarks`: open-market filter, largest-per-date, mark time equals a bar time, ≤10 per bar, `minSize` clamped to `[5, 14]`.
- `resolveSymbol`: every watchlist ticker; unknown symbol error; `daily_multipliers` and `visible_plots_set` present.
- Async assertions: no callback runs synchronously.
- Component: mock the `charting_library` module; assert the options object (library path, disabled features, no branding features disabled), that only one widget is created, and that unmount calls `remove()`.
- The library is absent in CI for contributors without access; tests mock it, and the build step skips the copy when the dependency is missing (with a warning, not a silent failure).

Manual QA: boot the panel, switch ticker, verify mark alignment and tooltip text, keyboard pass, 360/768/1440 px, slow-network and blocked-library states.

Effort (conditional; branch A only):

| Task | Days | Phase |
| --- | --- | --- |
| Licence gate + ADR-003 | 0.5 | P0 (inside the existing four days) |
| Widget boot spike with a stub datafeed | 0.5 | P0 |
| `tvDatafeed` + unit tests | 1.0 | P4 |
| `TvChartPanel`, theming, lazy loading | 0.5 | P4 |
| Manual QA and fixes | 0.5 | P4 |

The two P4 days come from the Timeline §6 contingency. If the schedule slips, UI-14 is the first thing cut — no Must depends on it.

Risks:

| Risk | Mitigation |
| --- | --- |
| Licence gate fails | Branch B; UI-06 unaffected |
| CI/Docker cannot get repository access | Stop before P4; do not vendor files; cut UI-14 |
| Library API changes between versions | Exact semver pin; feature-detect optional methods; datafeed contract tests |
| Mark size cannot match UI-06 | Documented deviation (§3); Recharts remains authoritative |
| Tooltips are plain text | Keep detail in the tape; do not promise rich tooltips |
| iframe escapes axe | Manual checklist; tape as equivalent path; state it in the QA report |
| Bundle weight | Lazy-loaded chunk; measure `pnpm build` before and after |
| Persisted settings leak between users | Settings persistence disabled (§5) |
| DST shifts a mark off its bar | Single time helper; DST tests; spike check |

## 10. Definition of done (UI-14)

- Gate evidence and ADR-003 merged.
- Panel renders the 6-month close line for the selected ticker, with ▲/▼ bar marks on the right dates and plain-text tooltips.
- No provider or vendor network call from the browser; only our API.
- Library files untracked, token build-only, attribution visible.
- Datafeed tests and the mocked component test pass; manual accessibility checklist attached to the PR.
- UI-06 still verified against the Recharts chart, and the release notes describe UI-14 as an optional technical view.
