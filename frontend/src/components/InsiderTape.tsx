import type { Txn } from "../api/types";
import { compactShares, compactCurrency, formatDate } from "../lib/format";

export type TapeFilter = "all" | "buys" | "csuite";

const FILTERS: { id: TapeFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "buys", label: "Buys only" },
  { id: "csuite", label: "C-suite" },
];

export function filterTxns(txns: Txn[], filter: TapeFilter): Txn[] {
  if (filter === "buys") return txns.filter((txn) => txn.action === "buy");
  if (filter === "csuite") {
    return txns.filter((txn) => txn.role === "CEO" || txn.role === "CFO");
  }
  return txns;
}

interface InsiderTapeProps {
  ticker: string | null;
  txns: Txn[];
  filter: TapeFilter;
  onFilterChange: (filter: TapeFilter) => void;
}

export function InsiderTape({ ticker, txns, filter, onFilterChange }: InsiderTapeProps) {
  const visible = filterTxns(txns, filter);

  return (
    <section aria-label="Insider transactions" className="panel flex h-[440px] flex-col">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
        <div>
          <h2 className="font-display text-xl font-semibold">Insider tape</h2>
          <p className="label mt-0.5" data-testid="tape-ticker">
            {ticker ?? "—"}
          </p>
        </div>
        <div role="group" aria-label="Filter transactions" className="flex gap-1">
          {FILTERS.map((option) => (
            <button
              key={option.id}
              type="button"
              aria-pressed={filter === option.id}
              onClick={() => onFilterChange(option.id)}
              className={`rounded-md border px-2.5 py-1 text-xs transition ${
                filter === option.id
                  ? "border-champagne/60 bg-champagne/10 text-champagne"
                  : "border-line text-muted hover:text-fg"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div className="scroll-slim flex-1 overflow-auto">
        {visible.length === 0 ? (
          <p role="status" className="p-6 text-sm text-muted">
            {txns.length === 0
              ? "No insider transactions in the lookback window."
              : "No transactions match this filter."}
          </p>
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead className="sticky top-0 z-10 bg-card">
              <tr className="border-b border-line text-left">
                <th scope="col" className="label px-2 py-2 font-medium sm:px-4">
                  Date
                </th>
                <th scope="col" className="label px-2 py-2 font-medium">
                  Insider
                </th>
                <th scope="col" className="label px-2 py-2 font-medium">
                  Type
                </th>
                <th scope="col" className="label hidden px-2 py-2 text-right font-medium sm:table-cell">
                  Shares
                </th>
                <th scope="col" className="label px-2 py-2 text-right font-medium sm:px-4">
                  Value
                </th>
              </tr>
            </thead>
            <tbody>
              {visible.map((txn) => (
                <tr
                  key={txn.key}
                  data-testid="tape-row"
                  data-action={txn.action}
                  className={`border-b border-line/60 align-top ${
                    txn.action === "other" ? "opacity-45" : ""
                  }`}
                >
                  <td className="whitespace-nowrap px-2 py-2.5 tnum text-muted sm:px-4">
                    {formatDate(txn.date)}
                  </td>
                  <td className="px-2 py-2.5">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-medium">{txn.name}</span>
                      {txn.starred ? (
                        <span
                          className="text-champagne"
                          title="CEO or CFO open-market purchase"
                        >
                          <span aria-hidden="true">★</span>
                          <span className="sr-only">CEO or CFO purchase</span>
                        </span>
                      ) : null}
                    </div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                      {txn.role ? <span className="text-xs text-muted">{txn.role}</span> : null}
                      {txn.is10b5_1 ? <Badge tone="muted">10b5-1</Badge> : null}
                    </div>
                  </td>
                  <td className="px-2 py-2.5">
                    <Badge tone={txn.action}>{txn.typeLabel}</Badge>
                  </td>
                  <td className="hidden px-2 py-2.5 text-right tnum sm:table-cell">
                    {compactShares(txn.shares)}
                  </td>
                  <td className="px-2 py-2.5 text-right tnum sm:px-4">
                    {txn.value === null ? (
                      <span title="No price reported">—</span>
                    ) : (
                      compactCurrency(txn.value)
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <p className="border-t border-line px-4 py-2 text-xs text-muted">
        Dimmed rows are awards, exercises, gifts and withholdings — shown but excluded from signals.
        ★ marks an open-market purchase by a CEO or CFO.
      </p>
    </section>
  );
}

function shortLabel(label: string): string {
  if (label === "Open-market buy") return "Buy";
  if (label === "Open-market sell") return "Sell";
  return label;
}

function Badge({ tone, children }: { tone: "buy" | "sell" | "other" | "muted"; children: string }) {
  const toneClass =
    tone === "buy"
      ? "border-buy/50 bg-buy/10 text-buy"
      : tone === "sell"
        ? "border-sell/50 bg-sell/10 text-sell"
        : "border-line bg-line/30 text-muted";

  const glyph = tone === "buy" ? "▲" : tone === "sell" ? "▼" : "";

  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded border px-1.5 py-0.5 text-[11px] ${toneClass}`}
    >
      {glyph ? <span aria-hidden="true">{glyph}</span> : null}
      {shortLabel(children) === children ? (
        children
      ) : (
        <>
          <span className="sm:hidden">{shortLabel(children)}</span>
          <span className="hidden sm:inline">{children}</span>
        </>
      )}
    </span>
  );
}
