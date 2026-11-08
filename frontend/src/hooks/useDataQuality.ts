import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";

export const DATA_QUALITY_KEY = ["data-quality"] as const;

export function useDataQuality() {
  return useQuery({
    queryKey: DATA_QUALITY_KEY,
    queryFn: () => api.dataQuality(),
    staleTime: 30_000,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });
}
