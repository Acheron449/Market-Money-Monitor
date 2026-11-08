import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";

const MINUTE = 60_000;

/** AUT-02: dashboard every 60 s, history and holders every 5 min, paused while hidden. */
export function useDashboard() {
  return useQuery({
    queryKey: ["dashboard"],
    queryFn: api.dashboard,
    refetchInterval: MINUTE,
    refetchIntervalInBackground: false,
  });
}

export function useHistory(ticker: string | null) {
  return useQuery({
    queryKey: ["history", ticker],
    queryFn: () => api.history(ticker ?? ""),
    enabled: ticker !== null,
    refetchInterval: 5 * MINUTE,
    refetchIntervalInBackground: false,
  });
}

export function useHolders(ticker: string | null) {
  return useQuery({
    queryKey: ["holders", ticker],
    queryFn: () => api.holders(ticker ?? ""),
    enabled: ticker !== null,
    refetchInterval: 5 * MINUTE,
    refetchIntervalInBackground: false,
  });
}
