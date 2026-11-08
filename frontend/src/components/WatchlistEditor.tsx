import { useState, type FormEvent } from "react";

import { MAX_TICKERS, normalizeSymbol, validateSymbol } from "../lib/watchlist";
import { useReplaceWatchlist, useWatchlist } from "../hooks/useWatchlist";

interface WatchlistEditorProps {
  onClose: () => void;
}

export function WatchlistEditor({ onClose }: WatchlistEditorProps) {
  const watchlist = useWatchlist();
  const save = useReplaceWatchlist();
  const [symbol, setSymbol] = useState("");
  const [error, setError] = useState<string | null>(null);
  const tickers = watchlist.data?.tickers ?? [];
  const busy = save.isPending;

  function persist(next: string[], onSaved?: () => void) {
    setError(null);
    save.mutate(next, {
      onSuccess: () => onSaved?.(),
      onError: (cause) =>
        setError(cause instanceof Error ? cause.message : "Could not save the watchlist."),
    });
  }

  function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const problem = validateSymbol(symbol, tickers);
    if (problem) {
      setError(problem);
      return;
    }
    persist([...tickers, normalizeSymbol(symbol)], () => setSymbol(""));
  }

  function remove(target: string) {
    if (tickers.length <= 1) {
      setError("Keep at least one ticker in the watchlist.");
      return;
    }
    persist(tickers.filter((ticker) => ticker !== target));
  }

  function move(index: number, delta: -1 | 1) {
    const destination = index + delta;
    if (destination < 0 || destination >= tickers.length) return;
    const next = [...tickers];
    const [moved] = next.splice(index, 1);
    if (!moved) return;
    next.splice(destination, 0, moved);
    persist(next);
  }

  return (
    <section
      aria-label="Watchlist editor"
      data-testid="watchlist-editor"
      className="panel mt-4 p-4 sm:p-5"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-xl font-semibold">Watchlist</h2>
          <p className="mt-0.5 text-xs text-muted">
            {tickers.length} of {MAX_TICKERS} tickers · changes save immediately
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close watchlist editor"
          className="rounded-md border border-line px-2.5 py-1 text-xs text-muted transition hover:border-champagne/50 hover:text-champagne"
        >
          Close
        </button>
      </div>

      {watchlist.isLoading ? (
        <div aria-busy="true" className="mt-4 space-y-2">
          <div className="skeleton h-9 w-full max-w-md" />
          <div className="skeleton h-8 w-56" />
        </div>
      ) : watchlist.isError ? (
        <div className="mt-4 flex flex-wrap items-center gap-3 text-sm text-sell" role="alert">
          <span>
            {watchlist.error instanceof Error
              ? watchlist.error.message
              : "Could not load the watchlist."}
          </span>
          <button
            type="button"
            onClick={() => void watchlist.refetch()}
            className="rounded-md border border-line px-2.5 py-1 text-xs text-fg hover:border-champagne/50 hover:text-champagne"
          >
            Retry
          </button>
        </div>
      ) : (
        <>
          <form onSubmit={add} className="mt-4 flex flex-wrap items-end gap-2">
            <div>
              <label htmlFor="watchlist-add" className="label">
                Add ticker
              </label>
              <input
                id="watchlist-add"
                data-testid="watchlist-add-input"
                value={symbol}
                onChange={(event) => {
                  setSymbol(event.target.value);
                  setError(null);
                }}
                placeholder="MSFT"
                maxLength={10}
                autoComplete="off"
                spellCheck={false}
                disabled={busy}
                className="mt-1 block w-36 rounded-md border border-line bg-bg/60 px-3 py-2 text-sm uppercase tracking-wide text-fg placeholder:normal-case placeholder:tracking-normal placeholder:text-muted/70 focus:border-champagne/60 disabled:opacity-60"
              />
            </div>
            <button
              type="submit"
              data-testid="watchlist-add"
              disabled={busy}
              className="rounded-md border border-champagne/50 bg-champagne/10 px-3 py-2 text-sm font-medium text-champagne transition hover:bg-champagne/20 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy ? "Saving…" : "Add"}
            </button>
          </form>

          {error ? (
            <p
              role="alert"
              data-testid="watchlist-error"
              className="mt-3 text-sm text-sell"
            >
              {error}
            </p>
          ) : null}

          <ol aria-label="Watchlist tickers" className="mt-4 max-w-xl space-y-1.5">
            {tickers.map((ticker, index) => (
              <li
                key={ticker}
                data-testid="watchlist-row"
                data-symbol={ticker}
                className="flex items-center justify-between gap-3 rounded-md border border-line/70 bg-bg/30 px-3 py-1.5"
              >
                <span className="font-display text-base font-semibold tracking-wide">
                  {ticker}
                </span>
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    aria-label={`Move ${ticker} up`}
                    onClick={() => move(index, -1)}
                    disabled={busy || index === 0}
                    className="rounded border border-line px-2 py-0.5 text-xs text-muted transition hover:border-champagne/50 hover:text-champagne disabled:cursor-not-allowed disabled:opacity-35"
                  >
                    <span aria-hidden="true">↑</span>
                  </button>
                  <button
                    type="button"
                    aria-label={`Move ${ticker} down`}
                    onClick={() => move(index, 1)}
                    disabled={busy || index === tickers.length - 1}
                    className="rounded border border-line px-2 py-0.5 text-xs text-muted transition hover:border-champagne/50 hover:text-champagne disabled:cursor-not-allowed disabled:opacity-35"
                  >
                    <span aria-hidden="true">↓</span>
                  </button>
                  <button
                    type="button"
                    aria-label={`Remove ${ticker}`}
                    onClick={() => remove(ticker)}
                    disabled={busy}
                    className="rounded border border-line px-2 py-0.5 text-xs text-muted transition hover:border-sell/60 hover:text-sell disabled:cursor-not-allowed disabled:opacity-35"
                  >
                    <span aria-hidden="true">×</span>
                  </button>
                </div>
              </li>
            ))}
          </ol>
          <p className="mt-3 text-xs text-muted">
            Add a resolved ticker, remove one, or move it up and down. Removing keeps its stored
            data for later.
          </p>
        </>
      )}
    </section>
  );
}
