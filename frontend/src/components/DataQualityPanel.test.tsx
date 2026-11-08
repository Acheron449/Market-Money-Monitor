import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { DataQuality } from "../api/types";
import { DataQualityPanel } from "./DataQualityPanel";

const quality: DataQuality = {
  crossCheck: {
    at: "2026-11-08T14:00:00Z",
    provider: "fixture_secondary",
    checked: 12,
    discrepancies: 2,
    status: "ok",
  },
  bulkInsider: { at: null, rows: 0, status: "never" },
  bulk13f: { at: "2026-11-08T13:00:00Z", rows: 2, status: "ok" },
  discrepancies: [
    {
      id: 2,
      checkedAt: "2026-11-08T14:00:00Z",
      symbol: "NVDA",
      accessionNo: "0001-26-000001",
      lineNo: 1,
      field: "value",
      primaryValue: 100000,
      secondaryValue: 120000,
      differencePct: 20,
      provider: "fixture_secondary",
    },
    {
      id: 1,
      checkedAt: "2026-11-08T14:00:00Z",
      symbol: "NVDA",
      accessionNo: "0001-26-000001",
      lineNo: 1,
      field: "shares",
      primaryValue: 1000,
      secondaryValue: 1200,
      differencePct: 20,
      provider: "fixture_secondary",
    },
  ],
};

describe("DataQualityPanel", () => {
  it("renders cross-check and bulk-load status with discrepancies", () => {
    render(
      <DataQualityPanel
        data={quality}
        loading={false}
        error={null}
        onRetry={() => {}}
        onClose={() => {}}
      />,
    );

    expect(screen.getByTestId("cross-check-summary")).toHaveTextContent("fixture_secondary");
    expect(screen.getByTestId("cross-check-summary")).toHaveTextContent("12 checked");
    expect(screen.getByTestId("cross-check-summary")).toHaveTextContent("2 discrepancies");
    expect(screen.getByTestId("bulk-insider-summary")).toHaveTextContent("No bulk load yet.");
    expect(screen.getByTestId("bulk-13f-summary")).toHaveTextContent("2 rows loaded");
    expect(screen.getAllByTestId("discrepancy-row")).toHaveLength(2);
    expect(screen.getByText("Value")).toBeInTheDocument();
    expect(screen.getByText("Shares")).toBeInTheDocument();
    expect(screen.getAllByText("20.0%")).toHaveLength(2);
  });

  it("shows the empty discrepancy state", () => {
    render(
      <DataQualityPanel
        data={{ ...quality, crossCheck: { ...quality.crossCheck, discrepancies: 0 }, discrepancies: [] }}
        loading={false}
        error={null}
        onRetry={() => {}}
        onClose={() => {}}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "No discrepancies above the 1% threshold.",
    );
  });

  it("shows an error and retries", async () => {
    const onRetry = vi.fn();
    render(
      <DataQualityPanel
        data={undefined}
        loading={false}
        error="fixture failure"
        onRetry={onRetry}
        onClose={() => {}}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("fixture failure");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
