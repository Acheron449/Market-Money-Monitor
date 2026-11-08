import type { Dashboard, Quote } from "../api/types";

/**
 * Merge an SSE quote frame into the cached dashboard. Only the incoming symbols
 * change; the quotes freshness entry follows the newest asOf so the bar stops
 * showing a stale quote source while the stream is healthy.
 */
export function mergeQuotes(
  current: Dashboard | undefined,
  incoming: Record<string, Quote>,
): Dashboard | undefined {
  if (!current) return current;

  const quotes = { ...current.quotes, ...incoming };
  const latest = Object.values(incoming).reduce<string | null>(
    (newest, quote) => (newest === null || quote.asOf > newest ? quote.asOf : newest),
    null,
  );
  if (latest === null) return { ...current, quotes };

  return {
    ...current,
    quotes,
    freshness: {
      ...current.freshness,
      quotes: { asOf: latest, stale: false },
    },
  };
}
