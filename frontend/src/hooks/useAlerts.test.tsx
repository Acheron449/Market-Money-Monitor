import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import type { Alert } from "../api/types";
import { ALERTS_KEY, useAlerts } from "./useAlerts";

const alert: Alert = {
  id: 1,
  kind: "cluster_buy",
  symbol: "AMZN",
  title: "Cluster buy: AMZN",
  body: "Three distinct insiders bought within 14 days.",
  createdAt: "2026-11-08T12:00:00Z",
  channels: ["telegram"],
  status: "delivered",
};

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  function wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }
  return { client, wrapper };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useAlerts", () => {
  it("loads recent alerts from the API", async () => {
    const spy = vi.spyOn(api, "alerts").mockResolvedValue([alert]);
    const { client, wrapper } = setup();

    const { result } = renderHook(() => useAlerts(), { wrapper });
    await waitFor(() => expect(result.current.data).toEqual([alert]));

    expect(spy).toHaveBeenCalledWith(20);
    expect(client.getQueryData(ALERTS_KEY)).toEqual([alert]);
  });
});
