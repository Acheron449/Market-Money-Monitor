import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import type { Txn } from "../api/types";
import { InsiderTape, type TapeFilter } from "./InsiderTape";

const txns: Txn[] = [
  {
    key: "1",
    ticker: "NVDA",
    date: "2026-11-05",
    name: "HUANG JEN HSUN",
    role: "CEO",
    action: "buy",
    typeLabel: "Open-market buy",
    shares: 10_000,
    value: 1_825_000,
    starred: true,
  },
  {
    key: "2",
    ticker: "NVDA",
    date: "2026-11-04",
    name: "COLEMAN DWIGHT",
    role: "CFO",
    action: "sell",
    typeLabel: "Open-market sell",
    shares: 2_500,
    value: 775_500,
    starred: false,
    is10b5_1: true,
  },
  {
    key: "3",
    ticker: "NVDA",
    date: "2026-11-03",
    name: "STEVENS MARK A",
    role: "Director",
    action: "other",
    typeLabel: "Award / grant",
    shares: 50,
    value: null,
    starred: false,
  },
];

function Harness() {
  const [filter, setFilter] = useState<TapeFilter>("all");
  return <InsiderTape ticker="NVDA" txns={txns} filter={filter} onFilterChange={setFilter} />;
}

describe("InsiderTape", () => {
  it("renders rows and dims non-open-market transactions", () => {
    render(<Harness />);
    expect(screen.getByText("HUANG JEN HSUN")).toBeInTheDocument();
    expect(screen.getByText("10b5-1")).toBeInTheDocument();

    const awardRow = screen.getByText("STEVENS MARK A").closest("tr");
    expect(awardRow).toHaveClass("opacity-45");
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("filters to buys and C-suite", async () => {
    render(<Harness />);

    await userEvent.click(screen.getByRole("button", { name: "Buys only" }));
    expect(screen.getByText("HUANG JEN HSUN")).toBeInTheDocument();
    expect(screen.queryByText("COLEMAN DWIGHT")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "C-suite" }));
    expect(screen.getByText("COLEMAN DWIGHT")).toBeInTheDocument();
    expect(screen.queryByText("STEVENS MARK A")).not.toBeInTheDocument();
  });

  it("shows an empty-state message when nothing matches", async () => {
    render(
      <InsiderTape
        ticker="NVDA"
        txns={[txns[2]!]}
        filter="buys"
        onFilterChange={() => {}}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("No transactions match this filter.");
  });
});
