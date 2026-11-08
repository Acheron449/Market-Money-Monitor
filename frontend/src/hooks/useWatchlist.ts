import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { Watchlist } from "../api/types";

export const WATCHLIST_KEY = ["watchlist"] as const;

export interface WatchlistWrite {
  tickers: string[];
  token: string;
}

export function useWatchlist() {
  return useQuery({
    queryKey: WATCHLIST_KEY,
    queryFn: api.watchlist,
    staleTime: 30_000,
  });
}

/**
 * Persist the whole watchlist, optimistically showing the new order and rolling
 * back to the server-backed list if the write is rejected. A successful write
 * invalidates the dashboard so tiles, the tape, signals and the SSE quote scope
 * all follow the new watchlist.
 */
export function useReplaceWatchlist() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ tickers, token }: WatchlistWrite) =>
      api.replaceWatchlist(tickers, token),
    onMutate: async ({ tickers }) => {
      await queryClient.cancelQueries({ queryKey: WATCHLIST_KEY });
      const previous = queryClient.getQueryData<Watchlist>(WATCHLIST_KEY);
      queryClient.setQueryData<Watchlist>(WATCHLIST_KEY, { tickers });
      return { previous };
    },
    onError: (_error, _tickers, context) => {
      if (context?.previous) {
        queryClient.setQueryData(WATCHLIST_KEY, context.previous);
      } else {
        void queryClient.invalidateQueries({ queryKey: WATCHLIST_KEY });
      }
    },
    onSuccess: (data) => {
      queryClient.setQueryData(WATCHLIST_KEY, data);
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}
