import { useCallback, useEffect } from "react";

import type { FilingNotice } from "../hooks/useQuoteStream";
import { compactCurrency } from "../lib/format";

interface FilingToastsProps {
  filings: FilingNotice[];
  onDismiss: (noticeId: string) => void;
}

const DISMISS_MS = 8000;

export function FilingToasts({ filings, onDismiss }: FilingToastsProps) {
  if (filings.length === 0) return null;
  return (
    <div
      role="region"
      aria-label="New filings"
      className="pointer-events-none fixed inset-x-4 bottom-4 z-50 flex flex-col items-end gap-2 sm:left-auto sm:w-[360px]"
    >
      {filings.map((filing) => (
        <FilingToast key={filing.noticeId} filing={filing} onDismiss={onDismiss} />
      ))}
    </div>
  );
}

function FilingToast({ filing, onDismiss }: { filing: FilingNotice; onDismiss: (id: string) => void }) {
  const dismiss = useCallback(() => onDismiss(filing.noticeId), [filing.noticeId, onDismiss]);

  useEffect(() => {
    const timer = window.setTimeout(dismiss, DISMISS_MS);
    return () => window.clearTimeout(timer);
  }, [dismiss]);

  const tone =
    filing.action === "buy" ? "text-buy" : filing.action === "sell" ? "text-sell" : "text-muted";
  const glyph = filing.action === "buy" ? "▲" : filing.action === "sell" ? "▼" : "";

  return (
    <div
      role="status"
      data-testid="filing-toast"
      data-ticker={filing.ticker}
      className="pointer-events-auto w-full rounded-xl border border-champagne/50 bg-card px-4 py-3 shadow-tile"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="label text-champagne">New Form 4 · {filing.ticker}</p>
          <p className="mt-1 text-sm font-medium">{filing.name}</p>
          <p className={`tnum mt-1 text-xs ${tone}`}>
            {glyph ? <span aria-hidden="true">{glyph} </span> : null}
            {filing.typeLabel} · {compactCurrency(filing.value)}
          </p>
        </div>
        <button
          type="button"
          aria-label={`Dismiss ${filing.ticker} filing`}
          onClick={dismiss}
          className="rounded border border-line px-1.5 py-0.5 text-xs text-muted transition hover:border-champagne/50 hover:text-champagne"
        >
          ×
        </button>
      </div>
    </div>
  );
}
