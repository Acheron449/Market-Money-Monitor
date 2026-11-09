import type { Dashboard, Quote } from "../api/types";

/**
 * Merge an SSE quote frame into the cached dashboard. Only the incoming symbols
 * change, and a tick can only make quotes fresher when its asOf is newer than
 * the stored freshness entry. During a provider outage the stream keeps
 * replaying the last-good rows with an old asOf, which must not clear the stale
 * badge (AC-04).
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

  const stored = current.freshness.quotes?.asOf ?? null;
  if (stored !== null && latest <= stored) return { ...current, quotes };

  return {
    ...current,
    quotes,
    freshness: {
      ...current.freshness,
      quotes: { asOf: latest, stale: false },
    },
  };
}
