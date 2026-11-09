import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { restoreQuoteFreshness, runFailureDrill } from "./failure-drill";

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

/**
 * AC-07: scan the live document with axe, using the WCAG 2.1 A/AA rule set.
 * Serious and critical findings fail the suite; no rule is disabled and no
 * element is excluded, so a regression in any of these states is a build break.
 */
async function scan(page: Page, state: string): Promise<void> {
  const results = await new AxeBuilder({ page }).withTags(WCAG).analyze();
  const blocking = results.violations.filter(
    (violation) => violation.impact === "serious" || violation.impact === "critical",
  );
  const detail = blocking
    .map(
      (violation) =>
        `${violation.id} [${violation.impact}] ${violation.help}\n  ${violation.nodes
          .slice(0, 4)
          .map((node) => node.target.join(" "))
          .join("\n  ")}`,
    )
    .join("\n");

  expect(results.passes.length, `${state}: axe ran no rules`).toBeGreaterThan(0);
  expect(blocking, `${state}: accessibility violations\n${detail}`).toEqual([]);
}

test("populated dashboard meets WCAG 2.1 AA", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("tile")).toHaveCount(8);
  await expect(page.getByTestId("holder-row")).toHaveCount(5);

  await scan(page, "populated dashboard");
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

  await scan(page, "open alert, data-quality and watchlist panels");
});

test("loading skeleton meets WCAG 2.1 AA", async ({ page }) => {
  await page.route("**/api/dashboard*", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 2500));
    await route.continue();
  });

  await page.goto("/");
  await expect(page.getByLabel("Loading dashboard")).toBeVisible();

  await scan(page, "loading skeleton");
});

test("empty watchlist meets WCAG 2.1 AA", async ({ page }) => {
  const body = (await (await page.request.get("/api/dashboard")).json()) as Record<string, unknown>;
  await page.route("**/api/dashboard*", (route) =>
    route.fulfill({ json: { ...body, signals: [], quotes: {}, tape: [] } }),
  );

  await page.goto("/");
  await expect(page.getByText("The watchlist is empty", { exact: false })).toBeVisible();

  await scan(page, "empty watchlist");
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

    await scan(page, "stale quotes with last-good data");
  } finally {
    restoreQuoteFreshness();
  }
});
