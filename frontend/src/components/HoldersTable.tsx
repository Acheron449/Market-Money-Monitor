import type { Holder } from "../api/types";
import { compactShares, compactCurrency, formatDate, signedPercent } from "../lib/format";

interface HoldersTableProps {
  ticker: string | null;
  holders: Holder[];
  loading: boolean;
}

export function HoldersTable({ ticker, holders, loading }: HoldersTableProps) {
  const reportPeriod = holders[0]?.reportPeriod ?? null;

  return (
    <section aria-label="Institutional holders" className="panel overflow-hidden">
      <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-line px-4 py-3">
        <h2 className="font-display text-xl font-semibold">Institutional holders</h2>
        <p className="label" data-testid="holders-ticker">
          {ticker ?? "—"}
          {reportPeriod ? ` · reported ${formatDate(reportPeriod)}` : ""}
        </p>
      </div>

      {loading ? (
        <div className="space-y-2 p-4" aria-hidden="true">
          {Array.from({ length: 5 }, (_, index) => (
            <div key={index} className="skeleton h-9 w-full" />
          ))}
        </div>
      ) : holders.length === 0 ? (
        <p role="status" className="p-6 text-sm text-muted">
          No 13F holdings reported for this ticker yet.
        </p>
      ) : (
        <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-line text-left">
              <th scope="col" className="label px-4 py-2 font-medium">
                #
              </th>
              <th scope="col" className="label px-2 py-2 font-medium">
                Institution
              </th>
              <th scope="col" className="label px-2 py-2 text-right font-medium">
                Shares
              </th>
              <th scope="col" className="label hidden px-2 py-2 text-right font-medium sm:table-cell">
                Value
              </th>
              <th scope="col" className="label px-2 py-2 text-right font-medium sm:px-4">
                QoQ
              </th>
            </tr>
          </thead>
          <tbody>
            {holders.map((holder) => (
              <tr
                key={`${holder.rank}-${holder.institution}`}
                data-testid="holder-row"
                className="border-b border-line/60"
              >
                <td className="px-4 py-2.5 tnum text-muted">{holder.rank}</td>
                <td className="px-2 py-2.5">{holder.institution}</td>
                <td className="px-2 py-2.5 text-right tnum">{compactShares(holder.shares)}</td>
                <td className="hidden px-2 py-2.5 text-right tnum sm:table-cell">
                  {compactCurrency(holder.value)}
                </td>
                <td
                  className={`px-2 py-2.5 text-right tnum sm:px-4 ${
                    holder.qoqChangePct === null
                      ? "text-muted"
                      : holder.qoqChangePct > 0
                        ? "text-buy"
                        : "text-sell"
                  }`}
                >
                  {holder.qoqChangePct === null ? (
                    <span title="No prior quarter">—</span>
                  ) : (
                    <>
                      <span aria-hidden="true">{holder.qoqChangePct > 0 ? "▲" : "▼"}</span>{" "}
                      {signedPercent(holder.qoqChangePct)}
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}
    </section>
  );
}
