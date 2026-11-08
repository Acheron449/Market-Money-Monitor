import { describe, expect, it } from "vitest";

import { meetsLatencyBudget, percentile } from "./latency";

describe("latency", () => {
  it("uses nearest-rank percentiles on unsorted samples", () => {
    const samples = Array.from({ length: 100 }, (_, index) => 100 - index);
    expect(percentile(samples, 50)).toBe(50);
    expect(percentile(samples, 95)).toBe(95);
    expect(percentile([12.5], 95)).toBe(12.5);
  });

  it("rejects empty samples and invalid quantiles", () => {
    expect(() => percentile([], 95)).toThrow("at least one sample");
    expect(() => percentile([1, 2], 0)).toThrow("quantile");
  });

  it("checks the p95 against the NFR-01 budget", () => {
    const under = Array.from({ length: 100 }, () => 120);
    const over = Array.from({ length: 20 }, () => 900);
    expect(meetsLatencyBudget(under, 300)).toBe(true);
    expect(meetsLatencyBudget(over, 300)).toBe(false);
    expect(meetsLatencyBudget([], 300)).toBe(false);
  });
});
