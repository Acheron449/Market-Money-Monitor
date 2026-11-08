import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import type { DataQuality } from "../api/types";
import { DATA_QUALITY_KEY, useDataQuality } from "./useDataQuality";

const quality: DataQuality = {
  crossCheck: {
    at: "2026-11-08T14:00:00Z",
    provider: "sec_edgar",
    checked: 10,
    discrepancies: 1,
    status: "ok",
  },
  bulkInsider: { at: null, rows: 0, status: "never" },
  reconciliation: { at: null, checked: 0, mismatches: 0, status: "never", error: null },
  bulk13f: { at: "2026-11-08T13:00:00Z", rows: 2, status: "ok" },
  discrepancies: [],
};

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }
  return { client, wrapper };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useDataQuality", () => {
  it("loads the quality summary from the API", async () => {
    const spy = vi.spyOn(api, "dataQuality").mockResolvedValue(quality);
    const { client, wrapper } = setup();

    const { result } = renderHook(() => useDataQuality(), { wrapper });
    await waitFor(() => expect(result.current.data).toEqual(quality));

    expect(spy).toHaveBeenCalledTimes(1);
    expect(client.getQueryData(DATA_QUALITY_KEY)).toEqual(quality);
  });
});
