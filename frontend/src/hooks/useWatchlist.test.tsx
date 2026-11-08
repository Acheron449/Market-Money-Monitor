import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import type { Watchlist } from "../api/types";
import { useReplaceWatchlist, useWatchlist, WATCHLIST_KEY } from "./useWatchlist";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function setup(initial: Watchlist = { tickers: ["NVDA", "AAPL"] }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  client.setQueryData(WATCHLIST_KEY, initial);
  function wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }
  return { client, wrapper };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useWatchlist", () => {
  it("loads the watchlist from the API", async () => {
    const spy = vi.spyOn(api, "watchlist").mockResolvedValue({ tickers: ["MSFT", "NVDA"] });
    const { client, wrapper } = setup();
    client.removeQueries({ queryKey: WATCHLIST_KEY });

    const { result } = renderHook(() => useWatchlist(), { wrapper });
    await waitFor(() => expect(result.current.data).toEqual({ tickers: ["MSFT", "NVDA"] }));
    expect(spy).toHaveBeenCalledTimes(1);
  });
});

describe("useReplaceWatchlist", () => {
  it("shows the new list optimistically and rolls back a rejected write", async () => {
    const pending = deferred<Watchlist>();
    const spy = vi.spyOn(api, "replaceWatchlist").mockReturnValue(pending.promise);
    const { client, wrapper } = setup();
    const { result } = renderHook(() => useReplaceWatchlist(), { wrapper });

    act(() => result.current.mutate({ tickers: ["NVDA", "MSFT"], token: "test-token" }));
    await waitFor(() =>
      expect(client.getQueryData(WATCHLIST_KEY)).toEqual({ tickers: ["NVDA", "MSFT"] }),
    );

    await act(async () => {
      pending.reject(new Error("ZZZZ is not in the known ticker universe"));
      await pending.promise.catch(() => undefined);
    });

    await waitFor(() =>
      expect(client.getQueryData(WATCHLIST_KEY)).toEqual({ tickers: ["NVDA", "AAPL"] }),
    );
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe("ZZZZ is not in the known ticker universe");
    expect(spy).toHaveBeenCalledWith(["NVDA", "MSFT"], "test-token");
  });

  it("stores the server-normalised order and invalidates the dashboard", async () => {
    vi.spyOn(api, "replaceWatchlist").mockResolvedValue({ tickers: ["MSFT", "NVDA"] });
    const { client, wrapper } = setup();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useReplaceWatchlist(), { wrapper });

    act(() => result.current.mutate({ tickers: ["msft", "nvda"], token: "test-token" }));

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(client.getQueryData(WATCHLIST_KEY)).toEqual({ tickers: ["MSFT", "NVDA"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["dashboard"] });
  });
});
