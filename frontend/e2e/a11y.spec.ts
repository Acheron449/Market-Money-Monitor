import { expect, test } from "@playwright/test";

import { scanPage } from "./axe";
import { restoreQuoteFreshness, runFailureDrill } from "./failure-drill";

test("populated dashboard meets WCAG 2.1 AA", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("tile")).toHaveCount(8);
  await expect(page.getByTestId("holder-row")).toHaveCount(5);

  await scanPage(page, "populated dashboard");
});

test("open panels meet WCAG 2.1 AA", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("tile")).toHaveCount(8);

  await page.getByRole("button", { name: "Alerts" }).click();
  await page.getByRole("button", { name: "Data quality" }).click();
  await page.getByRole("button", { name: "Edit watchlist" }).click();
  await expect(page.getByTestId("alerts-panel")).toBeVisible();
  await expect(page.getByTestId("data-quality-panel")).toBeVisible();
  await expect(page.getByTestId("watchlist-editor")).toBeVisible();

  await scanPage(page, "open alert, data-quality and watchlist panels");
});

test("loading skeleton meets WCAG 2.1 AA", async ({ page }) => {
  await page.route("**/api/dashboard*", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 2500));
    await route.continue();
  });

  await page.goto("/");
  await expect(page.getByLabel("Loading dashboard")).toBeVisible();

  await scanPage(page, "loading skeleton");
});

test("empty watchlist meets WCAG 2.1 AA", async ({ page }) => {
  const body = (await (await page.request.get("/api/dashboard")).json()) as Record<string, unknown>;
  await page.route("**/api/dashboard*", (route) =>
    route.fulfill({ json: { ...body, signals: [], quotes: {}, tape: [] } }),
  );

  await page.goto("/");
  await expect(page.getByText("The watchlist is empty", { exact: false })).toBeVisible();

  await scanPage(page, "empty watchlist");
});

test("stale last-good quotes meet WCAG 2.1 AA", async ({ page }) => {
  // A real outage: every provider fails and the stored rows age past the window,
  // so the live stream cannot legitimately freshen them again (AC-04).
  expect(runFailureDrill("outage")).toContain("outage: last-good kept");

  try {
    await page.goto("/");
    await expect(page.getByTestId("tile")).toHaveCount(8);
    await expect(page.getByTestId("freshness-stale-quotes")).toBeVisible();
    await expect(page.getByTestId("freshness-announcement")).toContainText("Stale data: Quotes");

    await scanPage(page, "stale quotes with last-good data");
  } finally {
    restoreQuoteFreshness();
  }
});
