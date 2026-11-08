import { expect, test, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

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
