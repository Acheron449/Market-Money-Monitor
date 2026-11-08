import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Quote, Signal } from "../api/types";
import { SignalTiles } from "./SignalTiles";

const signals: Signal[] = [
  { ticker: "NVDA", netValue: 12_000_000, txnCount: 4, starredCount: 2 },
  { ticker: "TSLA", netValue: -11_000_000, txnCount: 3, starredCount: 0 },
];

const quotes: Record<string, Quote> = {
  NVDA: {
    price: 182.5,
    changePct: 1.25,
    asOf: "2026-11-08T12:00:00Z",
    source: "alpaca",
    delayed: true,
  },
  TSLA: {
    price: 240,
    changePct: -2.1,
    asOf: "2026-11-08T12:00:00Z",
    source: "alpaca",
    delayed: true,
  },
};

describe("SignalTiles", () => {
  it("shows signed net values, counts and change", () => {
    render(<SignalTiles signals={signals} quotes={quotes} selected={null} onSelect={() => {}} />);

    expect(screen.getByText("+$12.0M")).toBeInTheDocument();
    expect(screen.getByText("-$11.0M")).toBeInTheDocument();
    expect(screen.getByText("+1.25%")).toBeInTheDocument();
    expect(screen.getByText("-2.10%")).toBeInTheDocument();
    expect(screen.getByText("4 txns")).toBeInTheDocument();
  });

  it("marks the selected tile and reports selection", async () => {
    const onSelect = vi.fn();
    render(
      <SignalTiles signals={signals} quotes={quotes} selected="NVDA" onSelect={onSelect} />,
    );

    const nvda = screen.getByRole("button", { name: /NVDA/ });
    const tsla = screen.getByRole("button", { name: /TSLA/ });
    expect(nvda).toHaveAttribute("aria-pressed", "true");
    expect(tsla).toHaveAttribute("aria-pressed", "false");

    await userEvent.click(tsla);
    expect(onSelect).toHaveBeenCalledWith("TSLA");
  });
});
