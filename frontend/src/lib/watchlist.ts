export const MAX_TICKERS = 50;
export const TICKER_RE = /^[A-Z][A-Z0-9.-]{0,9}$/;

export function normalizeSymbol(raw: string): string {
  return raw.trim().toUpperCase();
}

/** Client-side mirror of the API's symbol rules; unknown symbols are server-checked. */
export function validateSymbol(
  raw: string,
  tickers: string[],
  limit: number = MAX_TICKERS,
): string | null {
  const symbol = normalizeSymbol(raw);
  if (!symbol) return "Enter a ticker symbol.";
  if (!TICKER_RE.test(symbol)) {
    return "Use 1–10 letters, digits, dots or hyphens, starting with a letter.";
  }
  if (tickers.includes(symbol)) return `${symbol} is already in the watchlist.`;
  if (tickers.length >= limit) return `The watchlist is limited to ${limit} tickers.`;
  return null;
}
