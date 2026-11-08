import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";

export const ALERTS_KEY = ["alerts"] as const;

export function useAlerts() {
  return useQuery({
    queryKey: ALERTS_KEY,
    queryFn: () => api.alerts(20),
    staleTime: 30_000,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });
}
