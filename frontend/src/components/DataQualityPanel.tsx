import type { BulkLoadSummary, CrossCheckSummary, DataQuality, Discrepancy } from "../api/types";
import { compactCurrency, compactShares, formatDateTime } from "../lib/format";

interface DataQualityPanelProps {
  data: DataQuality | undefined;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onClose: () => void;
}

const STATUS_LABEL: Record<string, string> = {
  never: "Not run",
  running: "Running",
  ok: "OK",
  error: "Error",
};

function statusClass(status: string): string {
  if (status === "ok") return "border-buy/40 text-buy";
  if (status === "error") return "border-sell/40 text-sell";
  return "border-line text-muted";
}

function CrossCheck({ summary }: { summary: CrossCheckSummary }) {
  return (
    <div className="rounded-lg border border-line/80 p-3" data-testid="cross-check-summary">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-medium">Insider cross-check</h3>
        <span
          className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide ${statusClass(
            summary.status,
          )}`}
        >
          {STATUS_LABEL[summary.status] ?? summary.status}
        </span>
        {summary.at ? (
          <time dateTime={summary.at} className="ml-auto text-xs text-muted tnum">
            {formatDateTime(summary.at)}
          </time>
        ) : null}
      </div>
      {summary.at ? (
        <p className="mt-2 text-xs text-muted">
          <span className="text-fg/80">{summary.provider ?? "unknown provider"}</span>
          {" · "}
          {summary.checked} checked
          {" · "}
          <span className={summary.discrepancies > 0 ? "text-sell" : "text-buy"}>
            {summary.discrepancies} discrepancies
          </span>
        </p>
      ) : (
        <p className="mt-2 text-xs text-muted">No cross-check run yet.</p>
      )}
    </div>
  );
}

function BulkLoad({
  label,
  testId,
  summary,
}: {
  label: string;
  testId: string;
  summary: BulkLoadSummary;
}) {
  return (
    <div className="rounded-lg border border-line/80 p-3" data-testid={testId}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-medium">{label}</h3>
        <span
          className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide ${statusClass(
            summary.status,
          )}`}
        >
          {STATUS_LABEL[summary.status] ?? summary.status}
        </span>
        {summary.at ? (
          <time dateTime={summary.at} className="ml-auto text-xs text-muted tnum">
            {formatDateTime(summary.at)}
          </time>
        ) : null}
      </div>
      {summary.at ? (
        <p className="mt-2 text-xs text-muted">{summary.rows} rows loaded</p>
      ) : (
        <p className="mt-2 text-xs text-muted">No bulk load yet.</p>
      )}
    </div>
  );
}

function discrepancyValue(row: Discrepancy, value: number | null): string {
  if (row.field === "shares") return compactShares(value);
  return compactCurrency(value);
}

export function DataQualityPanel({
  data,
  loading,
  error,
  onRetry,
  onClose,
}: DataQualityPanelProps) {
  return (
    <section
      id="data-quality-panel"
      aria-label="Data quality"
      data-testid="data-quality-panel"
      className="panel mt-4 p-4 sm:p-5"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-xl font-semibold">Data quality</h2>
          <p className="mt-0.5 text-xs text-muted">
            Second-provider insider comparison and SEC bulk backfills.
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close data quality"
          className="rounded-md border border-line px-2.5 py-1 text-xs text-muted transition hover:border-champagne/50 hover:text-champagne"
        >
          Close
        </button>
      </div>

      {loading ? (
        <div aria-busy="true" className="mt-4 space-y-2">
          <div className="skeleton h-14 w-full" />
          <div className="skeleton h-14 w-full" />
        </div>
      ) : error ? (
        <div role="alert" className="mt-4 flex flex-wrap items-center gap-3 text-sm text-sell">
          <span>{error}</span>
          <button
            type="button"
            onClick={onRetry}
            className="rounded-md border border-line px-2.5 py-1 text-xs text-fg hover:border-champagne/50 hover:text-champagne"
          >
            Retry
          </button>
        </div>
      ) : data ? (
        <div className="mt-4 space-y-4">
          <CrossCheck summary={data.crossCheck} />
          <div className="grid gap-3 sm:grid-cols-2">
            <BulkLoad label="Insider data set" testId="bulk-insider-summary" summary={data.bulkInsider} />
            <BulkLoad label="Form 13F" testId="bulk-13f-summary" summary={data.bulk13f} />
          </div>

          <div>
            <h3 className="label">Differences above 1%</h3>
            {data.discrepancies.length === 0 ? (
              <p role="status" className="mt-2 text-sm text-muted">
                No discrepancies above the 1% threshold.
              </p>
            ) : (
              <ul aria-label="Cross-check discrepancies" className="mt-2 divide-y divide-line/70">
                {data.discrepancies.map((row) => (
                  <li
                    key={row.id}
                    data-testid="discrepancy-row"
                    className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2 text-sm"
                  >
                    <span className="font-display text-base font-semibold text-fg">
                      {row.symbol}
                    </span>
                    <span className="rounded-full border border-line px-2 py-0.5 text-[11px] text-muted">
                      {row.field === "shares" ? "Shares" : "Value"}
                    </span>
                    <span className="text-muted">
                      {discrepancyValue(row, row.primaryValue)}
                      {" → "}
                      <span className="text-fg">{discrepancyValue(row, row.secondaryValue)}</span>
                    </span>
                    <span className="text-sell tnum">{row.differencePct.toFixed(1)}%</span>
                    <span className="ml-auto text-xs text-muted">{row.provider}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
}
