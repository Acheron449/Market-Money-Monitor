import type { Freshness } from "../api/types";
import { relativeTime } from "../lib/format";

const SOURCES: { key: string; label: string }[] = [
  { key: "quotes", label: "Quotes" },
  { key: "filings", label: "Filings" },
  { key: "bars", label: "Bars" },
  { key: "holders", label: "Holders" },
];

interface FreshnessBarProps {
  freshness: Record<string, Freshness>;
  lookbackMonths: number;
}

export function FreshnessBar({ freshness, lookbackMonths }: FreshnessBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted">
      <span className="label">freshness</span>
      {SOURCES.map((source) => {
        const entry = freshness[source.key];
        const stale = entry?.stale ?? true;
        return (
          <span key={source.key} className="inline-flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className={`h-1.5 w-1.5 rounded-full ${stale ? "bg-sell" : "bg-buy"}`}
            />
            <span>{source.label}</span>
            <span className="tnum text-fg/80">{relativeTime(entry?.asOf ?? null)}</span>
            {stale ? (
              <span className="rounded border border-sell/40 px-1 py-0.5 text-[10px] uppercase tracking-wide text-sell">
                Stale
              </span>
            ) : null}
          </span>
        );
      })}
      <span className="ml-auto">Lookback {lookbackMonths} months</span>
    </div>
  );
}
