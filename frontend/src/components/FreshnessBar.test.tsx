import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Freshness } from "../api/types";
import { FreshnessBar } from "./FreshnessBar";

const freshness: Record<string, Freshness> = {
  quotes: { asOf: null, stale: true },
  filings: { asOf: "2026-11-08T12:00:00Z", stale: false },
  bars: { asOf: null, stale: true },
  holders: { asOf: null, stale: true },
};

describe("FreshnessBar", () => {
  it("marks only the stale sources", () => {
    render(<FreshnessBar freshness={freshness} lookbackMonths={6} />);

    expect(screen.getByTestId("freshness-stale-quotes")).toHaveTextContent("Stale");
    expect(screen.queryByTestId("freshness-stale-filings")).toBeNull();
    expect(screen.getByTestId("freshness-filings")).toHaveTextContent("Filings");
    expect(screen.getByText("Lookback 6 months")).toBeInTheDocument();
  });

  it("treats a missing source entry as stale", () => {
    render(<FreshnessBar freshness={{}} lookbackMonths={12} />);

    expect(screen.getByTestId("freshness-stale-quotes")).toBeVisible();
    expect(screen.getByTestId("freshness-stale-holders")).toBeVisible();
  });
});
