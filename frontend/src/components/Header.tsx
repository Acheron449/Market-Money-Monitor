import { relativeDays } from "../lib/format";

interface HeaderProps {
  latestFilingDate: string | null;
  refreshing: boolean;
  onRefresh: () => void;
}

export function Header({ latestFilingDate, refreshing, onRefresh }: HeaderProps) {
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

      <div className="flex items-center gap-4">
        <p className="text-sm text-muted" data-testid="filing-lag">
          Latest filing <span className="text-fg">{relativeDays(latestFilingDate)}</span>
        </p>
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
