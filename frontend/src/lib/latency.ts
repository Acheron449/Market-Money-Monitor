/** Nearest-rank latency percentiles for the AC-05 browser check (NFR-01). */

export function percentile(samples: number[], quantile: number): number {
  if (samples.length === 0) throw new Error("percentile needs at least one sample");
  if (!(quantile > 0 && quantile <= 100)) throw new Error("quantile must be in (0, 100]");
  const ordered = [...samples].sort((left, right) => left - right);
  const rank = Math.ceil((quantile / 100) * ordered.length);
  const value = ordered[Math.max(rank - 1, 0)];
  if (value === undefined) throw new Error("percentile index out of range");
  return value;
}

export function meetsLatencyBudget(samples: number[], budgetMs: number): boolean {
  return samples.length > 0 && percentile(samples, 95) <= budgetMs;
}
