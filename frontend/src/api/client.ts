import type { Dashboard, HistoryPoint, Holder, RefreshResponse, Watchlist } from "./types";

export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { message?: string };
      if (body.message) message = body.message;
    } catch {
      // keep the status message
    }
    throw new ApiError(response.status, message);
  }
  return (await response.json()) as T;
}

export const api = {
  dashboard: (exclude10b5_1 = false) =>
    request<Dashboard>(
      `/api/dashboard${exclude10b5_1 ? "?exclude10b5_1=true" : ""}`,
    ),
  history: (ticker: string) => request<HistoryPoint[]>(`/api/history/${encodeURIComponent(ticker)}`),
  holders: (ticker: string) => request<Holder[]>(`/api/holders/${encodeURIComponent(ticker)}`),
  refresh: () =>
    request<RefreshResponse>("/api/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    }),
  watchlist: () => request<Watchlist>("/api/watchlist"),
  replaceWatchlist: (tickers: string[], token: string) =>
    request<Watchlist>("/api/watchlist", {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ tickers }),
    }),
};
