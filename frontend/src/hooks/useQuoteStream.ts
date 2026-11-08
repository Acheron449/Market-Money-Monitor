import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { API_BASE, api } from "../api/client";
import type { Dashboard, Quote } from "../api/types";
import { mergeQuotes } from "../lib/quotes";

export type StreamStatus = "connecting" | "live" | "polling";

const POLL_INTERVAL_MS = 15_000;

/**
 * AUT-03: stream quote ticks over SSE; when the stream drops, fall back to a
 * 15 s dashboard poll. The stream reconnects on its own; a successful reopen
 * cancels the fallback. Everything is torn down on unmount.
 */
export function useQuoteStream(enabled: boolean): StreamStatus {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<StreamStatus>("connecting");
  const pollTimer = useRef<number | null>(null);

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

  return status;
}
