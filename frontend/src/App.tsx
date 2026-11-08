import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { api } from "./api/client";
import { FilingToasts } from "./components/FilingToasts";
import { Footer } from "./components/Footer";
import { FreshnessBar } from "./components/FreshnessBar";
import { Header } from "./components/Header";
import { HoldersTable } from "./components/HoldersTable";
import { InsiderTape, type TapeFilter } from "./components/InsiderTape";
import { PriceChart } from "./components/PriceChart";
import { SignalTiles } from "./components/SignalTiles";
import { DashboardSkeleton, ErrorState } from "./components/States";
import { WatchlistEditor } from "./components/WatchlistEditor";
import { useDashboard, useHistory, useHolders } from "./hooks/useMarketData";
import { useQuoteStream } from "./hooks/useQuoteStream";

export function App() {
  const queryClient = useQueryClient();
  const dashboard = useDashboard();
  const stream = useQuoteStream(dashboard.isSuccess);
  const [selected, setSelected] = useState<string | null>(null);
  const [filter, setFilter] = useState<TapeFilter>("all");
  const [editingWatchlist, setEditingWatchlist] = useState(false);

  const signals = useMemo(() => dashboard.data?.signals ?? [], [dashboard.data]);
  const activeTicker = useMemo(() => {
    if (selected && signals.some((signal) => signal.ticker === selected)) return selected;
    return signals[0]?.ticker ?? null;
  }, [selected, signals]);

  const history = useHistory(activeTicker);
  const holders = useHolders(activeTicker);

  const refresh = useMutation({
    mutationFn: api.refresh,
    onSuccess: () => {
      window.setTimeout(() => {
        void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      }, 1500);
    },
  });

  if (dashboard.isLoading) {
    return (
      <main className="mx-auto max-w-[1440px] px-4 py-6 sm:px-6 lg:px-8">
        <DashboardSkeleton />
      </main>
    );
  }

  if (dashboard.isError || !dashboard.data) {
    return (
      <main className="mx-auto max-w-[1440px] px-4 py-6 sm:px-6 lg:px-8">
        <ErrorState
          message={dashboard.error instanceof Error ? dashboard.error.message : undefined}
          onRetry={() => void dashboard.refetch()}
        />
      </main>
    );
  }

  const data = dashboard.data;
  const tape = data.tape.filter((txn) => txn.ticker === activeTicker);

  return (
    <main className="mx-auto max-w-[1440px] px-4 py-6 sm:px-6 lg:px-8">
      <Header
        latestFilingDate={data.latestFilingDate}
        refreshing={refresh.isPending}
        streamStatus={stream.status}
        editingWatchlist={editingWatchlist}
        onRefresh={() => refresh.mutate()}
        onEditWatchlist={() => setEditingWatchlist((open) => !open)}
      />

      <div className="mt-4">
        <FreshnessBar freshness={data.freshness} lookbackMonths={data.lookbackMonths} />
      </div>

      {editingWatchlist ? (
        <WatchlistEditor onClose={() => setEditingWatchlist(false)} />
      ) : null}

      <div className="mt-5">
        {signals.length === 0 ? (
          <p role="status" className="panel p-6 text-sm text-muted">
            The watchlist is empty. Add tickers with the watchlist editor.
          </p>
        ) : (
          <SignalTiles
            signals={signals}
            quotes={data.quotes}
            selected={activeTicker}
            onSelect={setSelected}
          />
        )}
      </div>

      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-[55fr_45fr]">
        <InsiderTape
          ticker={activeTicker}
          txns={tape}
          filter={filter}
          onFilterChange={setFilter}
        />
        <PriceChart
          ticker={activeTicker}
          history={history.data ?? []}
          txns={tape}
          loading={history.isLoading}
        />
      </div>

      <div className="mt-5">
        <HoldersTable
          ticker={activeTicker}
          holders={holders.data ?? []}
          loading={holders.isLoading}
        />
      </div>

      <Footer lookbackMonths={data.lookbackMonths} generatedAt={data.generatedAt} />

      <FilingToasts filings={stream.filings} onDismiss={stream.dismissFiling} />
    </main>
  );
}
