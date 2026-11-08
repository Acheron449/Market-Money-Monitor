import { expect, test, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

import { meetsLatencyBudget } from "../src/lib/latency";

const SHOTS = path.join(process.cwd(), "e2e", "screenshots");
const BACKEND = path.join(process.cwd(), "..", "backend");
const IGNORED_NETWORK = /fonts\.(googleapis|gstatic)\.com/;

/** Mutate the seeded quote row so the SSE stream has a real tick to publish. */
function writeQuote(symbol: string, price: number, changePct: number): void {
  const script = [
    "import datetime, sqlite3",
    "connection = sqlite3.connect('e2e.db', timeout=10)",
    "connection.execute(",
    '    "UPDATE quote SET price = ?, change_pct = ?, as_of = ? WHERE symbol = ?",',
    `    (${price}, ${changePct}, datetime.datetime.now(datetime.UTC).replace(tzinfo=None).isoformat(sep=" "), "${symbol}"),`,
    ")",
    "connection.commit()",
    "connection.close()",
  ].join("\n");
  execFileSync("uv", ["run", "python", "-c", script], {
    cwd: BACKEND,
    timeout: 30_000,
    stdio: "pipe",
  });
}

function runLoadTest(): string {
  return execFileSync(
    "uv",
    [
      "run",
      "python",
      "scripts/load_test.py",
      "--url",
      "http://127.0.0.1:8010",
      "--users",
      "50",
      "--requests",
      "3",
      "--warmup",
      "20",
      "--think-time-ms",
      "1000",
      "--ramp-ms",
      "20",
      "--max-p95-ms",
      "300",
    ],
    { cwd: BACKEND, timeout: 120_000, encoding: "utf8", stdio: "pipe" },
  );
}

function runReconciliation(): void {
  execFileSync("uv", ["run", "python", "scripts/e2e_reconciliation.py"], {
    cwd: BACKEND,
    env: { ...process.env, DATABASE_URL: "sqlite+aiosqlite:///./e2e.db" },
    timeout: 30_000,
    stdio: "pipe",
  });
}

function loadDataQualityFixtures(): void {
  execFileSync("uv", ["run", "python", "scripts/e2e_data_quality.py"], {
    cwd: BACKEND,
    env: { ...process.env, DATABASE_URL: "sqlite+aiosqlite:///./e2e.db" },
    timeout: 30_000,
    stdio: "pipe",
  });
}

function insertFiling(): void {
  execFileSync("uv", ["run", "python", "scripts/e2e_new_filing.py"], {
    cwd: BACKEND,
    env: { ...process.env, DATABASE_URL: "sqlite+aiosqlite:///./e2e.db" },
    timeout: 30_000,
    stdio: "pipe",
  });
}

function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    if (IGNORED_NETWORK.test(message.text())) return;
    errors.push(`console: ${message.text()}`);
  });
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
  page.on("requestfailed", (request) => {
    if (!request.url().includes("127.0.0.1")) return;
    errors.push(`request failed: ${request.url()} ${request.failure()?.errorText ?? ""}`);
  });
  return errors;
}

async function openDashboard(page: Page): Promise<void> {
  await page.goto("/");
  await expect(page.getByTestId("tile")).toHaveCount(8);
  await expect(page.getByTestId("filing-lag")).toContainText(/today|day/);
}

test("seeded dashboard: tiles, tape filters, chart markers, drill-down, disclaimer", async ({
  page,
}) => {
  const errors = collectErrors(page);
  await openDashboard(page);

  await expect(page.getByTestId("filing-lag")).toContainText("Latest filing");
  await expect(page.getByRole("heading", { name: "Smart Money Monitor" })).toBeVisible();
  await expect(page.getByText("insiders & institutions")).toBeVisible();

  const tiles = page.getByTestId("tile");
  await expect(tiles).toHaveCount(8);
  await expect(
    page.locator('[data-testid="tile"][data-ticker="AMZN"]').getByTestId("tile-cluster"),
  ).toBeVisible();
  const symbols = await tiles.evaluateAll((nodes) =>
    nodes.map((node) => node.getAttribute("data-ticker") ?? ""),
  );
  expect([...symbols].sort()).toEqual([
    "AAPL",
    "AMD",
    "AMZN",
    "COIN",
    "META",
    "NVDA",
    "PLTR",
    "TSLA",
  ]);

  // Sign-aware emphasis: NVDA is net positive, PLTR net negative.
  const nvda = page.locator('[data-testid="tile"][data-ticker="NVDA"]');
  const pltr = page.locator('[data-testid="tile"][data-ticker="PLTR"]');
  expect(Number(await nvda.getAttribute("data-net"))).toBeGreaterThan(0);
  expect(Number(await pltr.getAttribute("data-net"))).toBeLessThan(0);
  await expect(nvda.getByTestId("tile-net")).toHaveClass(/text-buy/);
  await expect(nvda.getByTestId("tile-net")).toContainText("+$2.2M");
  await expect(pltr.getByTestId("tile-net")).toHaveClass(/text-sell/);
  await expect(pltr.getByTestId("tile-net")).toContainText("-$140K");
  await expect(nvda.getByTestId("tile-stars")).toContainText("2");

  // Default selection is the first watchlist ticker.
  await expect(page.getByTestId("tape-ticker")).toHaveText("NVDA");
  await expect(page.getByTestId("tape-row")).toHaveCount(4);

  await page.getByRole("button", { name: "Buys only" }).click();
  await expect(page.getByTestId("tape-row")).toHaveCount(3);
  await page.getByRole("button", { name: "C-suite" }).click();
  await expect(page.getByTestId("tape-row")).toHaveCount(2);
  await page.getByRole("button", { name: "All" }).click();
  await expect(page.getByTestId("tape-row")).toHaveCount(4);

  // Non-open-market rows are dimmed and valueless (META has an award and a gift).
  await page.locator('[data-testid="tile"][data-ticker="META"]').click();
  await expect(page.getByTestId("tape-ticker")).toHaveText("META");
  const metaRows = page.getByTestId("tape-row");
  await expect(metaRows).toHaveCount(2);
  await expect(metaRows.first()).toHaveClass(/opacity-45/);
  await expect(metaRows.first()).toContainText("—");

  // PLTR has only a sale, so the buys filter is an empty state.
  await page.locator('[data-testid="tile"][data-ticker="PLTR"]').click();
  await page.getByRole("button", { name: "Buys only" }).click();
  await expect(page.getByRole("status")).toContainText("No transactions match this filter.");

  // Back to NVDA: three markers, radii exactly 5 + 9 × √(value ÷ max).
  await page.locator('[data-testid="tile"][data-ticker="NVDA"]').click();
  await page.getByRole("button", { name: "All" }).click();
  await expect(page.getByTestId("marker")).toHaveCount(3);

  const markers = await page.getByTestId("marker").evaluateAll((nodes) =>
    nodes.map((node) => ({
      date: node.getAttribute("data-date") ?? "",
      value: Number(node.getAttribute("data-value")),
      radius: Number(node.getAttribute("data-radius")),
    })),
  );
  const maxValue = Math.max(...markers.map((marker) => marker.value));
  expect(maxValue).toBe(1_825_000);
  expect(markers.map((marker) => marker.value).sort((a, b) => b - a)).toEqual([
    1_825_000, 900_000, 600_000,
  ]);
  for (const marker of markers) {
    expect(marker.radius).toBeCloseTo(5 + 9 * Math.sqrt(marker.value / maxValue), 2);
  }
  // One marker per date: the smaller same-day buy is not drawn.
  const dateCounts = new Map<string, number>();
  for (const marker of markers) dateCounts.set(marker.date, (dateCounts.get(marker.date) ?? 0) + 1);
  expect([...dateCounts.values()].every((count) => count === 1)).toBe(true);
  expect(markers.some((marker) => marker.value === 1_825_000)).toBe(true);

  const chart = page.getByTestId("price-chart");
  const svgBox = await chart.locator("svg").first().boundingBox();
  expect(svgBox).not.toBeNull();
  const markerTops: number[] = [];
  for (let index = 0; index < markers.length; index += 1) {
    const box = await page.getByTestId("marker").nth(index).boundingBox();
    expect(box).not.toBeNull();
    if (!box || !svgBox) continue;
    expect(box.x).toBeGreaterThanOrEqual(svgBox.x);
    expect(box.y).toBeGreaterThanOrEqual(svgBox.y);
    expect(box.x + box.width).toBeLessThanOrEqual(svgBox.x + svgBox.width);
    expect(box.y + box.height).toBeLessThanOrEqual(svgBox.y + svgBox.height);
    markerTops.push(Math.round(box.y));
  }
  expect(new Set(markerTops).size).toBeGreaterThan(1);

  // Drill-down: TSLA updates tape, chart and holders together.
  await page.locator('[data-testid="tile"][data-ticker="TSLA"]').click();
  await expect(page.getByTestId("tape-ticker")).toHaveText("TSLA");
  await expect(page.getByTestId("holders-ticker")).toContainText("TSLA");
  await expect(page.getByTestId("holder-row")).toHaveCount(5);
  await expect(chart.getByTestId("chart-canvas")).toHaveAttribute("aria-label", /TSLA/);
  await expect(page.getByTestId("holder-row").nth(2)).toContainText("—");
  await expect(page.getByTestId("marker")).toHaveCount(1);

  await expect(page.getByTestId("disclaimer")).toHaveText(
    "For information only — not investment advice.",
  );
  await expect(page.getByText(/Form 4 filings can lag by up to two business days/)).toBeVisible();

  expect(errors, "console, page or same-origin network errors").toEqual([]);
});

test("flags cluster buys and excludes 10b5-1 sales on demand", async ({ page }) => {
  const errors = collectErrors(page);
  await openDashboard(page);

  const dashboard = (await (await page.request.get("/api/dashboard")).json()) as {
    signals: { ticker: string; clusterBuy: boolean }[];
  };
  expect(dashboard.signals.find((signal) => signal.ticker === "AMZN")?.clusterBuy).toBe(true);
  await expect(
    page.locator('[data-testid="tile"][data-ticker="AMZN"]').getByTestId("tile-cluster"),
  ).toBeVisible();

  const coin = page.locator('[data-testid="tile"][data-ticker="COIN"]');
  await expect(coin).toHaveAttribute("data-net", "-775500");
  await expect(coin.getByTestId("tile-net")).toContainText("-$776K");

  const toggle = page.getByTestId("exclude-10b5-1");
  await expect(toggle).not.toBeChecked();
  await toggle.check();

  await expect(coin).toHaveAttribute("data-net", "0");
  await expect(coin.getByTestId("tile-net")).toContainText("$0");
  await expect(coin).toContainText("1 txns");

  // Excluding from net never removes the flagged row from the tape.
  await coin.click();
  await expect(page.getByTestId("tape-row")).toHaveCount(1);
  await expect(page.getByTestId("tape-row").getByText("10b5-1")).toBeVisible();

  await toggle.uncheck();
  await expect(coin).toHaveAttribute("data-net", "-775500");
  await expect(coin.getByTestId("tile-net")).toContainText("-$776K");

  expect(errors, "console, page or same-origin network errors").toEqual([]);
});

test("manual refresh returns 202 then 429 inside the cooldown", async ({ page }) => {
  const errors = collectErrors(page);
  await openDashboard(page);

  const first = page.waitForResponse(
    (response) => response.url().includes("/api/refresh") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: /Refresh/ }).click();
  expect((await first).status()).toBe(202);
  await expect(page.getByRole("button", { name: "Refresh" })).toBeEnabled();

  const second = page.waitForResponse(
    (response) => response.url().includes("/api/refresh") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Refresh" }).click();
  expect((await second).status()).toBe(429);

  await expect(page.getByTestId("tile")).toHaveCount(8);
  // The deliberate 429 is the documented throttle response; the browser logs it.
  expect(
    errors.filter((error) => !error.includes("429")),
    "console, page or same-origin network errors",
  ).toEqual([]);
});

test("loading skeleton, error state and Retry", async ({ page }) => {
  let failing = true;
  await page.route("**/api/dashboard", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 700));
    if (failing) {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ code: "boom", message: "fixture failure" }),
      });
      return;
    }
    await route.continue();
  });

  await page.goto("/");
  await expect(page.locator('[aria-busy="true"]')).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("fixture failure");

  failing = false;
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByTestId("tile")).toHaveCount(8);
});

test("empty holders state renders", async ({ page }) => {
  await page.route("**/api/holders/*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );
  await openDashboard(page);
  await expect(page.getByText("No 13F holdings reported for this ticker yet.")).toBeVisible();
});

test("streams live quote ticks and falls back to polling", async ({ page }) => {
  await openDashboard(page);
  const status = page.getByTestId("stream-status");
  await expect(status).toHaveAttribute("data-status", "live");
  await expect(status).toContainText("Live quotes");

  const coin = page.locator('[data-testid="tile"][data-ticker="COIN"]');
  try {
    writeQuote("COIN", 299.99, -1.23);
    await expect(coin).toContainText("-1.23%");
  } finally {
    writeQuote("COIN", 310.2, -0.65);
  }

  await page.route("**/api/stream", (route) => route.abort());
  let dashboardCalls = 0;
  page.on("response", (response) => {
    if (response.url().includes("/api/dashboard")) dashboardCalls += 1;
  });
  await page.reload();
  await expect(status).toHaveAttribute("data-status", "polling");
  await expect(page.getByTestId("tile")).toHaveCount(8);
  // Reload fetch, the immediate fallback poll, then the 15 s interval poll.
  await expect.poll(() => dashboardCalls, { timeout: 30_000 }).toBeGreaterThanOrEqual(3);
});

test("no horizontal overflow at 360, 768 and 1440", async ({ page }) => {
  fs.mkdirSync(SHOTS, { recursive: true });

  for (const width of [360, 768, 1440]) {
    await page.setViewportSize({ width, height: width === 360 ? 780 : 900 });
    await page.goto("/");
    await expect(page.getByTestId("tile")).toHaveCount(8);
    await expect(page.getByTestId("holder-row")).toHaveCount(5);
    await page.waitForTimeout(400);

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, `horizontal overflow at ${width}px`).toBeLessThanOrEqual(1);

    await page.screenshot({
      path: path.join(SHOTS, `dashboard-${width}.png`),
      fullPage: true,
    });
  }

  // The two-pane row is side-by-side on desktop and stacked on mobile.
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await expect(page.getByTestId("tile")).toHaveCount(8);
  const wideTape = await page.getByTestId("tape-ticker").boundingBox();
  const wideChart = await page.getByTestId("price-chart").boundingBox();
  expect(wideTape).not.toBeNull();
  expect(wideChart).not.toBeNull();
  if (wideTape && wideChart) expect(wideChart.x).toBeGreaterThan(wideTape.x);

  await page.setViewportSize({ width: 360, height: 780 });
  await page.goto("/");
  await expect(page.getByTestId("tile")).toHaveCount(8);
  const narrowTape = await page.getByTestId("tape-ticker").boundingBox();
  const narrowChart = await page.getByTestId("price-chart").boundingBox();
  expect(narrowTape).not.toBeNull();
  expect(narrowChart).not.toBeNull();
  if (narrowTape && narrowChart) {
    expect(narrowChart.y).toBeGreaterThan(narrowTape.y);
  }
});

test("watchlist editor persists additions, removals and order", async ({ page }) => {
  const errors = collectErrors(page);
  await openDashboard(page);

  await page.getByRole("button", { name: "Edit watchlist" }).click();
  await expect(page.getByTestId("watchlist-editor")).toBeVisible();
  await expect(page.getByTestId("watchlist-row")).toHaveCount(8);
  await page.getByTestId("watchlist-token").fill("e2e-admin-token");

  // The editor stays inside a 360 px viewport.
  await page.setViewportSize({ width: 360, height: 780 });
  const editorOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(editorOverflow, "watchlist editor horizontal overflow at 360px").toBeLessThanOrEqual(1);
  await page.setViewportSize({ width: 1440, height: 900 });

  const input = page.getByTestId("watchlist-add-input");
  const add = page.getByTestId("watchlist-add");

  // Client-side shape rejection stays in the editor.
  await input.fill("not a ticker");
  await add.click();
  await expect(page.getByTestId("watchlist-error")).toContainText("Use 1–10 letters");
  await expect(page.getByTestId("watchlist-row")).toHaveCount(8);

  // A well-formed symbol outside the resolved universe is rejected by the API.
  await input.fill("ZZZZ");
  await add.click();
  await expect(page.getByTestId("watchlist-error")).toContainText(
    "ZZZZ is not in the known ticker universe",
  );
  await expect(page.getByTestId("tile")).toHaveCount(8);

  // Add the resolved off-watchlist fixture and wait for the dashboard to follow.
  await input.fill("msft");
  await add.click();
  await expect(page.getByTestId("watchlist-row")).toHaveCount(9);
  await expect(page.getByTestId("tile")).toHaveCount(9);

  const msft = page.locator('[data-testid="tile"][data-ticker="MSFT"]');
  await expect(msft).toBeVisible();

  // The SSE stream's subscription scope follows the active watchlist.
  try {
    writeQuote("MSFT", 420.42, 1.5);
    await expect(msft).toContainText("+1.50%");
  } finally {
    writeQuote("MSFT", 415.2, 0.65);
  }

  // The newly active ticker renders its tape, chart and holders.
  await msft.click();
  await expect(page.getByTestId("tape-ticker")).toHaveText("MSFT");
  await expect(page.getByTestId("tape-row")).toHaveCount(2);
  await expect(page.getByTestId("marker")).toHaveCount(2);
  await expect(page.getByTestId("holder-row")).toHaveCount(5);
  await expect(page.getByTestId("price-chart").getByTestId("chart-canvas")).toHaveAttribute(
    "aria-label",
    /MSFT/,
  );

  // Remove a different ticker and reorder the new one.
  await page.getByRole("button", { name: "Remove AAPL" }).click();
  await expect(page.getByTestId("watchlist-row")).toHaveCount(8);
  await expect(page.locator('[data-testid="tile"][data-ticker="AAPL"]')).toHaveCount(0);
  await page.getByRole("button", { name: "Move MSFT up" }).click();

  const expectedOrder = ["NVDA", "TSLA", "AMZN", "META", "AMD", "PLTR", "MSFT", "COIN"];
  await expect
    .poll(async () =>
      page.getByTestId("tile").evaluateAll((nodes) =>
        nodes.map((node) => node.getAttribute("data-ticker") ?? ""),
      ),
    )
    .toEqual(expectedOrder);

  // The change is server-side, so a full reload keeps the new watchlist.
  await page.getByRole("button", { name: "Close watchlist editor" }).click();
  await page.reload();
  await expect(page.getByTestId("tile")).toHaveCount(8);
  await expect(page.locator('[data-testid="tile"][data-ticker="MSFT"]')).toBeVisible();
  await expect(page.locator('[data-testid="tile"][data-ticker="AAPL"]')).toHaveCount(0);
  const orderAfterReload = await page
    .getByTestId("tile")
    .evaluateAll((nodes) => nodes.map((node) => node.getAttribute("data-ticker") ?? ""));
  expect(orderAfterReload).toEqual(expectedOrder);

  const persisted = (await (await page.request.get("/api/watchlist")).json()) as {
    tickers: string[];
  };
  expect(persisted.tickers).toEqual(expectedOrder);

  // Two errors are intentional here: the 422 from the rejected symbol and the
  // EventSource abort as reload tears down the page. Nothing else may appear.
  const unexpected = errors.filter(
    (error) =>
      !(error.includes("422 (Unprocessable Entity)") && error.includes("Failed to load resource")) &&
      !(error.includes("/api/stream") && error.includes("net::ERR_ABORTED")),
  );
  expect(unexpected, "unexpected console, page or same-origin network errors").toEqual([]);
});

test("shows persisted alert history for triggered filings", async ({ page }) => {
  const errors = collectErrors(page);
  await openDashboard(page);

  await page.getByTestId("alerts-toggle").click();
  const panel = page.getByTestId("alerts-panel");
  await expect(panel).toBeVisible();
  await expect(panel.getByRole("heading", { name: "Alerts" })).toBeVisible();

  const rows = panel.getByTestId("alert-row");
  await expect(rows.first()).toBeVisible();
  await expect(panel).toContainText("CEO/CFO buy");
  await expect(panel).toContainText("Recorded — no channel configured");
  await expect(panel).toContainText("NVDA");

  await page.getByRole("button", { name: "Close alerts" }).click();
  await expect(panel).toHaveCount(0);

  expect(errors, "console, page or same-origin network errors").toEqual([]);
});

test("toasts a new Form 4 and refreshes the tape", async ({ page }) => {
  const errors = collectErrors(page);
  await openDashboard(page);
  await expect(page.getByTestId("stream-status")).toHaveAttribute("data-status", "live");
  await expect(page.getByTestId("filing-toast")).toHaveCount(0);

  insertFiling();

  const toast = page.getByTestId("filing-toast");
  await expect(toast).toHaveCount(1, { timeout: 15_000 });
  await expect(toast).toContainText("New Form 4 · NVDA");
  await expect(toast).toContainText("HUANG JEN HSUN");
  await expect(toast).toContainText("Open-market buy");
  await expect(toast).toContainText("$222K");

  const nvda = page.locator('[data-testid="tile"][data-ticker="NVDA"]');
  await expect(page.getByTestId("tape-row")).toHaveCount(5);
  await expect(nvda.getByTestId("tile-net")).toContainText("+$2.4M");

  await page.getByRole("button", { name: "Dismiss NVDA filing" }).click();
  await expect(toast).toHaveCount(0);

  expect(errors, "console, page or same-origin network errors").toEqual([]);
});

test("serves the dashboard inside the NFR-01 budget at 50 concurrent users", async ({
  page,
}) => {
  const errors = collectErrors(page);

  const output = runLoadTest();
  expect(output).toContain("50 users x 3 requests (150 total");
  expect(output).toContain("0 errors");
  expect(output).toContain("pass");
  const measured = Number(/p95 ([\d.]+) ms/.exec(output)?.[1]);
  expect(measured).toBeGreaterThan(0);
  expect(measured).toBeLessThanOrEqual(300);

  // The real browser still renders, and the same endpoint answers inside the
  // budget for sequential browser fetches after the concurrent run.
  await openDashboard(page);
  const samples = await page.evaluate(async () => {
    const values: number[] = [];
    for (let index = 0; index < 20; index += 1) {
      const started = performance.now();
      const response = await fetch("/api/dashboard");
      if (!response.ok) throw new Error(`dashboard responded ${response.status}`);
      await response.json();
      values.push(performance.now() - started);
    }
    return values;
  });
  expect(samples).toHaveLength(20);
  expect(meetsLatencyBudget(samples, 300)).toBe(true);

  expect(errors, "console, page or same-origin network errors").toEqual([]);
});

test("reconciles Form 4 filings against the frozen EDGAR snapshot", async ({ page }) => {
  const errors = collectErrors(page);
  await openDashboard(page);

  runReconciliation();
  await page.reload();

  await page.getByTestId("data-quality-toggle").click();
  const panel = page.getByTestId("data-quality-panel");
  await expect(panel).toBeVisible();
  const summary = panel.getByTestId("reconciliation-summary");
  await expect(summary).toContainText("40 checked");
  await expect(summary).toContainText("0 mismatches");
  await expect(summary).toContainText("OK");
  await expect(panel.getByText("No reconciliation run yet.")).toHaveCount(0);

  const quality = (await (await page.request.get("/api/data-quality")).json()) as {
    reconciliation: { checked: number; mismatches: number; status: string; error: string | null };
  };
  expect(quality.reconciliation.checked).toBe(40);
  expect(quality.reconciliation.mismatches).toBe(0);
  expect(quality.reconciliation.status).toBe("ok");
  expect(quality.reconciliation.error).toBeNull();

  const unexpected = errors.filter(
    (error) => !(error.includes("/api/stream") && error.includes("net::ERR_ABORTED")),
  );
  expect(unexpected, "unexpected console, page or same-origin network errors").toEqual([]);
});

test("shows SEC 13F backfill and insider cross-check discrepancies", async ({ page }) => {
  const errors = collectErrors(page);
  await openDashboard(page);

  loadDataQualityFixtures();
  await page.reload();

  await expect(page.getByText("BULK 13F CAPITAL LLC")).toBeVisible();
  await expect(page.getByTestId("holder-row")).toHaveCount(6);

  await page.getByTestId("data-quality-toggle").click();
  const panel = page.getByTestId("data-quality-panel");
  await expect(panel).toBeVisible();
  await expect(panel.getByTestId("cross-check-summary")).toContainText("fixture_secondary");
  await expect(panel.getByTestId("cross-check-summary")).toContainText("2 discrepancies");
  await expect(panel.getByTestId("bulk-13f-summary")).toContainText("2 rows loaded");
  await expect(panel.getByTestId("discrepancy-row")).toHaveCount(2);
  await expect(panel.getByText("Sh", { exact: true })).toHaveCount(0);
  await expect(panel.getByText("Shares", { exact: true })).toBeVisible();
  await expect(panel.getByText("Value", { exact: true })).toBeVisible();
  await expect(panel.getByText("20.0%").first()).toBeVisible();

  // The reload above deliberately tears down the open SSE stream.
  const unexpected = errors.filter(
    (error) => !(error.includes("/api/stream") && error.includes("net::ERR_ABORTED")),
  );
  expect(unexpected, "unexpected console, page or same-origin network errors").toEqual([]);
});
