import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import type { Dashboard, Quote, Txn } from "../api/types";
import { useQuoteStream } from "./useQuoteStream";

type Listener = (event: Event) => void;

class MockEventSource {
  static instances: MockEventSource[] = [];
  readonly url: string;
  onopen: ((event: Event) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  closed = false;
  private listeners = new Map<string, Listener>();

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: Listener): void {
    this.listeners.set(type, listener);
  }

  close(): void {
    this.closed = true;
  }

  open(): void {
    this.onopen?.(new Event("open"));
  }

  fail(): void {
    this.onerror?.(new Event("error"));
  }

  emit(type: string, payload: unknown): void {
    this.listeners.get(type)?.({ data: JSON.stringify(payload) } as unknown as Event);
  }
}

const quote: Quote = {
  price: 182.5,
  changePct: 1.25,
  asOf: "2026-11-08T12:00:00Z",
  source: "fixtures",
  delayed: true,
};

const filing: Txn = {
  key: "0001045810-26-000099:1",
  ticker: "NVDA",
  date: "2026-11-09",
  name: "HUANG JEN HSUN",
  role: "CEO",
  action: "buy",
  typeLabel: "Open-market buy",
  shares: 1200,
  value: 222000,
  starred: true,
  is10b5_1: false,
};

const dashboard: Dashboard = {
  signals: [{ ticker: "NVDA", netValue: 1000, txnCount: 1, starredCount: 0 }],
  quotes: { NVDA: quote },
  tape: [],
  lookbackMonths: 6,
  latestFilingDate: "2026-11-08",
  generatedAt: "2026-11-08T12:00:00Z",
  freshness: { quotes: { asOf: quote.asOf, stale: false } },
};

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(["dashboard"], dashboard);
  function wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }
  const rendered = renderHook(() => useQuoteStream(true), { wrapper });
  const source = MockEventSource.instances.at(-1);
  if (!source) throw new Error("EventSource was not opened");
  return { client, source, ...rendered };
}

beforeEach(() => {
  MockEventSource.instances = [];
  vi.stubGlobal("EventSource", MockEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("useQuoteStream", () => {
  it("opens the stream, merges ticks and reports live", () => {
    const { client, source, result } = setup();
    expect(source.url).toBe("/api/stream");
    expect(result.current.status).toBe("connecting");

    act(() => source.open());
    expect(result.current.status).toBe("live");

    act(() =>
      source.emit("quotes", {
        quotes: { NVDA: { ...quote, price: 190.25, changePct: 2.75 } },
      }),
    );

    const cached = client.getQueryData<Dashboard>(["dashboard"]);
    expect(cached?.quotes.NVDA?.price).toBe(190.25);
    expect(cached?.quotes.NVDA?.changePct).toBe(2.75);
    expect(result.current.status).toBe("live");
  });

  it("turns new filings into toast notices and dismisses them", () => {
    const { source, result } = setup();
    act(() => source.open());

    act(() => source.emit("filings", { filings: [filing] }));
    expect(result.current.filings).toHaveLength(1);
    expect(result.current.filings[0]?.ticker).toBe("NVDA");
    expect(result.current.filings[0]?.name).toBe("HUANG JEN HSUN");
    expect(result.current.filings[0]?.value).toBe(222000);

    act(() => result.current.dismissFiling(result.current.filings[0]?.noticeId ?? ""));
    expect(result.current.filings).toHaveLength(0);
  });

  it("falls back to a 15 s poll when the stream errors and stops on unmount", async () => {
    vi.useFakeTimers();
    const spy = vi.spyOn(api, "dashboard").mockResolvedValue(dashboard);
    const { client, source, result, unmount } = setup();

    act(() => source.fail());
    expect(result.current.status).toBe("polling");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(spy).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });
    expect(spy).toHaveBeenCalledTimes(2);
    expect(client.getQueryData<Dashboard>(["dashboard"])?.quotes.NVDA?.price).toBe(182.5);

    unmount();
    expect(source.closed).toBe(true);
    await vi.advanceTimersByTimeAsync(30_000);
    expect(spy).toHaveBeenCalledTimes(2);
  });
});
