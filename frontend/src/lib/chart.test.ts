import { describe, expect, it } from "vitest";

import type { HistoryPoint, Txn } from "../api/types";
import { buildChartRows, buildMarkers, markerRadius } from "./chart";

const txn = (overrides: Partial<Txn>): Txn => ({
  key: "k",
  ticker: "NVDA",
  date: "2026-11-05",
  name: "INSIDER",
  role: "CEO",
  action: "buy",
  typeLabel: "Open-market buy",
  shares: 100,
  value: 1_000_000,
  starred: true,
  ...overrides,
});

describe("markerRadius", () => {
  it("follows 5 + 9 × √(value ÷ max)", () => {
    expect(markerRadius(0, 100)).toBe(5);
    expect(markerRadius(25, 100)).toBeCloseTo(9.5);
    expect(markerRadius(100, 100)).toBeCloseTo(14);
  });

  it("never returns less than 5 px", () => {
    expect(markerRadius(-10, 100)).toBe(5);
    expect(markerRadius(10, 0)).toBe(5);
  });
});

describe("buildMarkers", () => {
  it("keeps one marker per date, largest value wins", () => {
    const markers = buildMarkers([
      txn({ key: "a", date: "2026-11-05", value: 1_000_000 }),
      txn({ key: "b", date: "2026-11-05", action: "sell", value: 3_000_000 }),
      txn({ key: "c", date: "2026-11-06", value: 500_000 }),
    ]);
    expect(markers).toHaveLength(2);
    expect(markers.find((marker) => marker.date === "2026-11-05")?.action).toBe("sell");
    expect(markers.find((marker) => marker.date === "2026-11-05")?.value).toBe(3_000_000);
  });

  it("ignores non-open-market rows and rows without value", () => {
    const markers = buildMarkers([
      txn({ action: "other", typeLabel: "Award / grant", value: 9_000_000 }),
      txn({ key: "v", value: null }),
      txn({ key: "ok" }),
    ]);
    expect(markers).toHaveLength(1);
  });
});

describe("buildChartRows", () => {
  it("aligns markers to closes and labels the axis value", () => {
    const history: HistoryPoint[] = [
      { date: "2026-11-04", close: 178 },
      { date: "2026-11-05", close: 182.5 },
    ];
    const rows = buildChartRows(history, buildMarkers([txn({})]));
    expect(rows[0]).toMatchObject({ date: "2026-11-04", close: 178, marker: null, buy: null });
    expect(rows[1]).toMatchObject({ date: "2026-11-05", close: 182.5, buy: 182.5 });
  });
});
