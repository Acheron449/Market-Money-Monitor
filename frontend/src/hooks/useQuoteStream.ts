import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { API_BASE, api } from "../api/client";
import type { Dashboard, Quote, Txn } from "../api/types";
import { mergeQuotes } from "../lib/quotes";

export type StreamStatus = "connecting" | "live" | "polling";

export interface FilingNotice extends Txn {
  noticeId: string;
}

export interface MarketStreamState {
  status: StreamStatus;
  filings: FilingNotice[];
  dismissFiling: (noticeId: string) => void;
}

const POLL_INTERVAL_MS = 15_000;
const MAX_TOASTS = 3;

/**
 * AUT-03: stream quote ticks over SSE; when the stream drops, fall back to a
 * 15 s dashboard poll. The stream reconnects on its own; a successful reopen
 * cancels the fallback.
 *
 * AUT-07: fresh Form 4 rows arrive as `filings` frames, become toast notices
 * and invalidate the dashboard so the tape and signals catch up.
 */
export function useQuoteStream(enabled: boolean): MarketStreamState {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<StreamStatus>("connecting");
  const [filings, setFilings] = useState<FilingNotice[]>([]);
  const pollTimer = useRef<number | null>(null);
  const sequence = useRef(0);

  const dismissFiling = useCallback((noticeId: string) => {
    setFilings((current) => current.filter((filing) => filing.noticeId !== noticeId));
  }, []);

  useEffect(() => {
    if (!enabled) return;

    let cancelled = false;
    let source: EventSource | null = null;

    const stopPolling = () => {
      if (pollTimer.current !== null) {
        window.clearInterval(pollTimer.current);
        pollTimer.current = null;
      }
    };

    const poll = async () => {
      if (document.visibilityState === "hidden") return;
      try {
        const dashboard = await api.dashboard();
        if (!cancelled) queryClient.setQueryData(["dashboard"], dashboard);
      } catch {
        // Keep the last good snapshot; the next tick retries.
      }
    };

    const startPolling = () => {
      if (pollTimer.current !== null) return;
      void poll();
      pollTimer.current = window.setInterval(() => void poll(), POLL_INTERVAL_MS);
    };

    source = new EventSource(`${API_BASE}/api/stream`);

    source.onopen = () => {
      if (cancelled) return;
      stopPolling();
      setStatus("live");
    };

    source.addEventListener("quotes", (event) => {
      if (cancelled) return;
      try {
        const payload = JSON.parse((event as MessageEvent).data as string) as {
          quotes: Record<string, Quote>;
        };
        queryClient.setQueryData<Dashboard>(["dashboard"], (current) =>
          mergeQuotes(current, payload.quotes),
        );
        setStatus("live");
      } catch {
        // Ignore malformed frames; polling still serves the last good data.
      }
    });

    source.addEventListener("filings", (event) => {
      if (cancelled) return;
      try {
        const payload = JSON.parse((event as MessageEvent).data as string) as {
          filings?: Txn[];
        };
        const incoming = payload.filings ?? [];
        if (incoming.length === 0) return;
        const notices = incoming.map((txn) => ({
          ...txn,
          noticeId: `${txn.key}:${sequence.current++}`,
        }));
        setFilings((current) => [...notices, ...current].slice(0, MAX_TOASTS));
        void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      } catch {
        // A malformed filing frame must not break the quote stream.
      }
    });

    source.onerror = () => {
      if (cancelled) return;
      setStatus("polling");
      startPolling();
    };

    return () => {
      cancelled = true;
      source?.close();
      stopPolling();
    };
  }, [enabled, queryClient]);

  return { status, filings, dismissFiling };
}
