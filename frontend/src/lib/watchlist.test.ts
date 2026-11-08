import { describe, expect, it } from "vitest";

import { normalizeSymbol, validateSymbol } from "./watchlist";

describe("watchlist validation", () => {
  it("normalises case and surrounding whitespace", () => {
    expect(normalizeSymbol("  msft ")).toBe("MSFT");
  });

  it("requires a symbol", () => {
    expect(validateSymbol("   ", ["NVDA"])).toBe("Enter a ticker symbol.");
  });

  it("rejects malformed symbols", () => {
    expect(validateSymbol("not a ticker", ["NVDA"])).toMatch(/Use 1–10 letters/);
    expect(validateSymbol("1NVDA", ["NVDA"])).toMatch(/Use 1–10 letters/);
    expect(validateSymbol("A".repeat(11), ["NVDA"])).toMatch(/Use 1–10 letters/);
  });

  it("rejects duplicates after normalisation", () => {
    expect(validateSymbol(" nvda ", ["NVDA", "AAPL"])).toBe(
      "NVDA is already in the watchlist.",
    );
  });

  it("enforces the 50-ticker limit", () => {
    const full = Array.from({ length: 50 }, (_, index) => `T${index}`);
    expect(validateSymbol("MSFT", full)).toBe("The watchlist is limited to 50 tickers.");
  });

  it("accepts letters, digits, dots and hyphens", () => {
    expect(validateSymbol(" msft ", ["NVDA"])).toBeNull();
    expect(validateSymbol("BRK.B", ["NVDA"])).toBeNull();
    expect(validateSymbol("A-B2", ["NVDA"])).toBeNull();
  });
});
