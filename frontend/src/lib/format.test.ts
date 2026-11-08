import { describe, expect, it } from "vitest";

import {
  compactCurrency,
  direction,
  emphasisClass,
  relativeDays,
  relativeTime,
  signedCompactCurrency,
  signedPercent,
  trendGlyph,
} from "./format";

describe("compactCurrency", () => {
  it("formats magnitudes with $K/$M/$B/$T", () => {
    expect(compactCurrency(950)).toBe("$950");
    expect(compactCurrency(1_825_000)).toBe("$1.8M");
    expect(compactCurrency(2_400_000_000)).toBe("$2.4B");
    expect(compactCurrency(1_200_000_000_000)).toBe("$1.2T");
  });

  it("shows an em dash for null", () => {
    expect(compactCurrency(null)).toBe("—");
    expect(compactCurrency(undefined)).toBe("—");
  });

  it("signs net values explicitly", () => {
    expect(signedCompactCurrency(1_000_000)).toBe("+$1.0M");
    expect(signedCompactCurrency(-11_000_000)).toBe("-$11.0M");
    expect(signedCompactCurrency(0)).toBe("$0");
  });
});

describe("signal tone", () => {
  it("is sign-aware, not magnitude-only", () => {
    expect(emphasisClass(-12_000_000)).toContain("sell");
    expect(emphasisClass(12_000_000)).toContain("buy");
    expect(emphasisClass(-500_000)).toBe("border-line");
  });

  it("keeps a glyph and sign alongside colour", () => {
    expect(trendGlyph(1.2)).toBe("▲");
    expect(trendGlyph(-0.4)).toBe("▼");
    expect(trendGlyph(0)).toBe("■");
    expect(signedPercent(1.234)).toBe("+1.23%");
    expect(signedPercent(-0.4)).toBe("-0.40%");
    expect(direction(0)).toBe("flat");
  });
});

describe("relative time", () => {
  const now = new Date("2026-11-08T12:00:00Z");

  it("formats ages for freshness", () => {
    expect(relativeTime("2026-11-08T11:59:48Z", now)).toBe("12 s ago");
    expect(relativeTime("2026-11-08T11:56:00Z", now)).toBe("4 min ago");
    expect(relativeTime("2026-11-08T08:00:00Z", now)).toBe("4 h ago");
    expect(relativeTime(null, now)).toBe("never");
  });

  it("formats filing lag in days", () => {
    expect(relativeDays("2026-11-08", now)).toBe("today");
    expect(relativeDays("2026-11-06", now)).toBe("2 days ago");
    expect(relativeDays(null, now)).toBe("no filings yet");
  });
});
