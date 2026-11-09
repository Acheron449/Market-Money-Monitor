import type { Quote, Signal } from "../api/types";
import {
  direction,
  emphasisClass,
  signedCompactCurrency,
  signedPercent,
  trendGlyph,
} from "../lib/format";

interface SignalTilesProps {
  signals: Signal[];
  quotes: Record<string, Quote>;
  selected: string | null;
  onSelect: (ticker: string) => void;
}

export function SignalTiles({ signals, quotes, selected, onSelect }: SignalTilesProps) {
  return (
    <section aria-label="Ticker signals" className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-8">
      {signals.map((signal) => {
        const quote = quotes[signal.ticker];
        const change = quote?.changePct ?? null;
        const trend = direction(change);
        const isSelected = signal.ticker === selected;
        const netTone =
          signal.netValue > 0 ? "text-buy" : signal.netValue < 0 ? "text-sell" : "text-fg";

        return (
          <button
            key={signal.ticker}
            type="button"
            data-testid="tile"
            data-ticker={signal.ticker}
            data-net={signal.netValue}
            aria-pressed={isSelected}
            onClick={() => onSelect(signal.ticker)}
            className={`group flex flex-col gap-2 rounded-xl border bg-card/80 p-3.5 text-left shadow-tile transition hover:border-champagne/50 ${
              isSelected ? "border-champagne ring-1 ring-champagne" : emphasisClass(signal.netValue)
            }`}
          >
            <div className="flex items-baseline justify-between gap-2">
              <span className="font-display text-lg font-semibold tracking-wide">
                {signal.ticker}
              </span>
              <span
                className={`tnum text-xs font-medium ${
                  trend === "up" ? "text-buy" : trend === "down" ? "text-sell" : "text-muted"
                }`}
              >
                <span aria-hidden="true">{trendGlyph(change)}</span> {signedPercent(change)}
              </span>
            </div>

            <div className="flex items-baseline justify-between gap-2">
              <span className={`tnum text-lg font-semibold ${netTone}`} data-testid="tile-net">
                {signedCompactCurrency(signal.netValue)}
              </span>
              <span className="label">net</span>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
              <div className="flex items-center gap-1.5">
                <span className="tnum">{signal.txnCount} txns</span>
                {quote ? (
                  <span
                    role="img"
                    data-testid="tile-source"
                    aria-label={`Quote source: ${quote.source}`}
                    title={`Quote source: ${quote.source}`}
                    className="rounded border border-line px-1 py-0.5 text-[10px] uppercase tracking-wide"
                  >
                    {quote.source}
                  </span>
                ) : null}
              </div>
              <div className="flex items-center gap-1.5">
                {signal.clusterBuy ? (
                  <span
                    role="img"
                    data-testid="tile-cluster"
                    aria-label="Cluster buy: three or more insiders bought within 14 days"
                    className="rounded border border-champagne/50 bg-champagne/10 px-1 py-0.5 text-[10px] font-medium uppercase tracking-wide text-champagne"
                  >
                    Cluster
                  </span>
                ) : null}
                <span className="tnum inline-flex items-center gap-1" data-testid="tile-stars">
                  <span aria-hidden="true" className="text-champagne">
                    ★
                  </span>
                  {signal.starredCount}
                  <span className="sr-only">CEO or CFO purchases</span>
                </span>
              </div>
            </div>
          </button>
        );
      })}
    </section>
  );
}
