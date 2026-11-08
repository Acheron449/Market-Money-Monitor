import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Alert } from "../api/types";
import { AlertsPanel } from "./AlertsPanel";

const alerts: Alert[] = [
  {
    id: 2,
    kind: "ceo_cfo_buy",
    symbol: "NVDA",
    title: "CEO/CFO open-market buy: NVDA",
    body: "HUANG JEN HSUN (CEO) bought 1000 shares of NVDA on 2026-11-08 for $222,000.",
    createdAt: "2026-11-08T12:00:00Z",
    channels: ["webhook"],
    status: "delivered",
  },
  {
    id: 1,
    kind: "net_crossing",
    symbol: "AAPL",
    title: "Net signal crossed +$10,000,000: AAPL",
    body: "AAPL crossed above the threshold.",
    createdAt: "2026-11-08T11:00:00Z",
    channels: [],
    status: "recorded",
  },
];

describe("AlertsPanel", () => {
  it("renders triggers, bodies and delivery channels", () => {
    render(
      <AlertsPanel
        alerts={alerts}
        loading={false}
        error={null}
        onRetry={() => {}}
        onClose={() => {}}
      />,
    );

    expect(screen.getByTestId("alerts-panel")).toBeInTheDocument();
    expect(screen.getAllByTestId("alert-row")).toHaveLength(2);
    expect(screen.getByText("CEO/CFO buy")).toBeInTheDocument();
    expect(screen.getByText("Net crossing")).toBeInTheDocument();
    expect(screen.getByText("Sent via webhook")).toBeInTheDocument();
    expect(screen.getByText("Recorded — no channel configured")).toBeInTheDocument();
    expect(screen.getAllByTestId("alert-row")[0]).toHaveAttribute("data-kind", "ceo_cfo_buy");
  });

  it("shows an empty state", () => {
    render(
      <AlertsPanel
        alerts={[]}
        loading={false}
        error={null}
        onRetry={() => {}}
        onClose={() => {}}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("No alerts yet.");
  });

  it("shows a load error and retries", async () => {
    const onRetry = vi.fn();
    render(
      <AlertsPanel
        alerts={[]}
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
