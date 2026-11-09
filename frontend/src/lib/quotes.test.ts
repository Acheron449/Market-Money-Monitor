import { describe, expect, it } from "vitest";

import type { Dashboard, Quote } from "../api/types";
import { mergeQuotes } from "./quotes";

const baseQuote: Quote = {
  price: 182.5,
  changePct: 1.25,
  asOf: "2026-11-08T12:00:00Z",
  source: "fixtures",
  delayed: true,
};

const dashboard: Dashboard = {
  signals: [
    { ticker: "NVDA", netValue: 1000, txnCount: 1, starredCount: 0, clusterBuy: false },
  ],
  quotes: { NVDA: baseQuote },
  tape: [],
  lookbackMonths: 6,
  latestFilingDate: "2026-11-08",
  generatedAt: "2026-11-08T12:00:00Z",
  freshness: { quotes: { asOf: "2026-11-08T12:00:00Z", stale: true } },
};

describe("mergeQuotes", () => {
  it("merges only the incoming symbols and keeps the rest", () => {
    const tick: Quote = {
      ...baseQuote,
      price: 190.25,
      changePct: 2.75,
      asOf: "2026-11-08T12:01:00Z",
    };
    const merged = mergeQuotes(dashboard, { NVDA: tick });

    expect(merged?.quotes.NVDA?.price).toBe(190.25);
    expect(merged?.signals).toBe(dashboard.signals);
    expect(merged?.freshness.quotes).toEqual({ asOf: tick.asOf, stale: false });
  });

  it("keeps the stale flag when a tick replays last-good data", () => {
    const replay: Quote = { ...baseQuote, asOf: "2026-11-08T11:00:00Z" };
    const merged = mergeQuotes(dashboard, { NVDA: replay });

    expect(merged?.quotes.NVDA?.asOf).toBe(replay.asOf);
    expect(merged?.freshness.quotes).toEqual({
      asOf: "2026-11-08T12:00:00Z",
      stale: true,
    });
  });

  it("uses the newest incoming asOf for quote freshness", () => {
    const merged = mergeQuotes(dashboard, {
      NVDA: { ...baseQuote, asOf: "2026-11-08T12:05:00Z" },
      AAPL: { ...baseQuote, asOf: "2026-11-08T12:03:00Z" },
    });

    expect(merged?.freshness.quotes?.asOf).toBe("2026-11-08T12:05:00Z");
    expect(merged?.freshness.quotes?.stale).toBe(false);
  });

  it("returns undefined until the dashboard has loaded", () => {
    expect(mergeQuotes(undefined, { NVDA: baseQuote })).toBeUndefined();
  });
});
