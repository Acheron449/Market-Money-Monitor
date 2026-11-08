import type { Alert } from "../api/types";
import { formatDateTime } from "../lib/format";

interface AlertsPanelProps {
  alerts: Alert[];
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onClose: () => void;
}

const KIND_LABEL: Record<string, string> = {
  ceo_cfo_buy: "CEO/CFO buy",
  large_transaction: "Large transaction",
  net_crossing: "Net crossing",
  cluster_buy: "Cluster buy",
};

function channelSummary(alert: Alert): string {
  if (alert.channels.length > 0) return `Sent via ${alert.channels.join(", ")}`;
  if (alert.status === "failed") return "Delivery failed";
  return "Recorded — no channel configured";
}

export function AlertsPanel({ alerts, loading, error, onRetry, onClose }: AlertsPanelProps) {
  return (
    <section
      id="alerts-panel"
      aria-label="Alerts"
      data-testid="alerts-panel"
      className="panel mt-4 p-4 sm:p-5"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-xl font-semibold">Alerts</h2>
          <p className="mt-0.5 text-xs text-muted">
            CEO/CFO buys, large transactions, ±$10M net crossings and cluster buys.
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close alerts"
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
      ) : alerts.length === 0 ? (
        <p role="status" className="mt-4 text-sm text-muted">
          No alerts yet. They appear after an insider ingest triggers a rule.
        </p>
      ) : (
        <ul aria-label="Alert history" className="mt-4 divide-y divide-line/70">
          {alerts.map((alert) => (
            <li
              key={alert.id}
              data-testid="alert-row"
              data-kind={alert.kind}
              className="py-3 first:pt-1 last:pb-0"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full border border-champagne/30 bg-champagne/10 px-2 py-0.5 text-[11px] font-medium text-champagne">
                  {KIND_LABEL[alert.kind] ?? alert.kind}
                </span>
                <span className="font-display text-base font-semibold tracking-wide text-fg">
                  {alert.symbol}
                </span>
                <span className="text-sm text-fg">{alert.title}</span>
                <time
                  dateTime={alert.createdAt}
                  className="ml-auto text-xs text-muted tnum"
                >
                  {formatDateTime(alert.createdAt)}
                </time>
              </div>
              <p className="mt-1 text-sm text-muted">{alert.body}</p>
              <p className="mt-1 text-xs text-muted">{channelSummary(alert)}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
