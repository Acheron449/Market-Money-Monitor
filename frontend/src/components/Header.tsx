import type { StreamStatus } from "../hooks/useQuoteStream";
import { relativeDays } from "../lib/format";

interface HeaderProps {
  latestFilingDate: string | null;
  refreshing: boolean;
  streamStatus: StreamStatus;
  editingWatchlist: boolean;
  alertsOpen: boolean;
  alertsCount: number;
  dataQualityOpen: boolean;
  onRefresh: () => void;
  onEditWatchlist: () => void;
  onToggleAlerts: () => void;
  onToggleDataQuality: () => void;
}

const STREAM_LABEL: Record<StreamStatus, string> = {
  connecting: "Connecting…",
  live: "Live quotes",
  polling: "Polling 15s",
};

export function Header({
  latestFilingDate,
  refreshing,
  streamStatus,
  editingWatchlist,
  alertsOpen,
  alertsCount,
  dataQualityOpen,
  onRefresh,
  onEditWatchlist,
  onToggleAlerts,
  onToggleDataQuality,
}: HeaderProps) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-4 border-b border-line pb-5">
      <div className="flex items-center gap-4">
        <div
          aria-hidden="true"
          className="grid h-11 w-11 place-items-center rounded-lg border border-champagne/40 bg-card font-display text-lg text-champagne"
        >
          SM
        </div>
        <div>
          <h1 className="font-display text-3xl font-semibold leading-none tracking-tight">
            Smart Money Monitor
          </h1>
          <p className="label mt-1.5">insiders &amp; institutions</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 sm:gap-4">
        <span
          data-testid="stream-status"
          data-status={streamStatus}
          title={
            streamStatus === "live"
              ? "Quote ticks are streaming"
              : streamStatus === "polling"
                ? "Stream unavailable; refreshing quotes every 15 seconds"
                : "Opening the quote stream"
          }
          className="inline-flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-xs text-muted"
        >
          <span
            aria-hidden="true"
            className={`h-1.5 w-1.5 rounded-full ${
              streamStatus === "live" ? "bg-buy" : "bg-champagne"
            }`}
          />
          {STREAM_LABEL[streamStatus]}
        </span>
        <p className="text-sm text-muted" data-testid="filing-lag">
          Latest filing <span className="text-fg">{relativeDays(latestFilingDate)}</span>
        </p>
        <button
          type="button"
          onClick={onToggleAlerts}
          aria-expanded={alertsOpen}
          aria-controls="alerts-panel"
          data-testid="alerts-toggle"
          className="inline-flex items-center gap-2 rounded-lg border border-line bg-card px-3.5 py-2 text-sm font-medium text-fg transition hover:border-champagne/50 hover:text-champagne"
        >
          <span aria-hidden="true" className="text-champagne">
            ◈
          </span>
          Alerts
          {alertsCount > 0 ? (
            <span
              data-testid="alerts-count"
              className="rounded-full border border-champagne/30 bg-champagne/10 px-1.5 text-[11px] text-champagne"
            >
              {alertsCount}
            </span>
          ) : null}
        </button>
        <button
          type="button"
          onClick={onToggleDataQuality}
          aria-expanded={dataQualityOpen}
          aria-controls="data-quality-panel"
          data-testid="data-quality-toggle"
          className="inline-flex items-center gap-2 rounded-lg border border-line bg-card px-3.5 py-2 text-sm font-medium text-fg transition hover:border-champagne/50 hover:text-champagne"
        >
          <span aria-hidden="true" className="text-champagne">
            ◫
          </span>
          Data quality
        </button>
        <button
          type="button"
          onClick={onEditWatchlist}
          aria-expanded={editingWatchlist}
          className="inline-flex items-center gap-2 rounded-lg border border-line bg-card px-3.5 py-2 text-sm font-medium text-fg transition hover:border-champagne/50 hover:text-champagne"
        >
          <span aria-hidden="true" className="text-champagne">
            ☰
          </span>
          {editingWatchlist ? "Hide watchlist" : "Edit watchlist"}
        </button>
        <button
          type="button"
          onClick={onRefresh}
          disabled={refreshing}
          aria-busy={refreshing}
          className="inline-flex items-center gap-2 rounded-lg border border-line bg-card px-3.5 py-2 text-sm font-medium text-fg transition hover:border-champagne/50 hover:text-champagne disabled:cursor-not-allowed disabled:opacity-70"
        >
          <span
            aria-hidden="true"
            className={`inline-block h-3.5 w-3.5 rounded-full border-2 border-champagne border-t-transparent ${
              refreshing ? "animate-spin" : ""
            }`}
          />
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>
    </header>
  );
}
