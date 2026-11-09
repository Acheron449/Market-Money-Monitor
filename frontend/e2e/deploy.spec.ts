import { expect, test } from "@playwright/test";

import { scanPage } from "./axe";

const IGNORED_NETWORK = /fonts\.(googleapis|gstatic)\.com/;

/**
 * Runs against the production build served by `vite preview` (SPA fallback plus
 * the same reverse-proxy paths as `ops/nginx.conf`) and a backend started with
 * `ENVIRONMENT=production` after `alembic upgrade head` on an empty database.
 */
test("production build serves the dashboard, assets and health checks", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    if (IGNORED_NETWORK.test(message.text())) return;
    errors.push(`console: ${message.text()}`);
  });
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));

  const health = await page.request.get("/healthz");
  expect(health.status()).toBe(200);
  expect(await health.json()).toEqual({ status: "ok" });

  const ready = await page.request.get("/readyz");
  expect(ready.status()).toBe(200);
  expect(await ready.json()).toEqual({ status: "ready" });

  const dashboard = await page.request.get("/api/dashboard");
  expect(dashboard.status()).toBe(200);
  const body = (await dashboard.json()) as {
    signals: { ticker: string }[];
    quotes: Record<string, { price: number; source: string }>;
    holders?: unknown[];
  };
  expect(body.signals).toHaveLength(8);
  expect(body.quotes.NVDA?.price).toBeCloseTo(182.5, 2);
  expect(body.quotes.NVDA?.source).toBe("fixtures");

  const index = await page.request.get("/");
  expect(index.status()).toBe(200);
  const html = await index.text();
  expect(html).toContain('<div id="root">');

  const assets = [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map(
    (match) => match[1] as string,
  );
  expect(assets.length, "the built index references hashed assets").toBeGreaterThanOrEqual(2);
  for (const asset of assets) {
    const response = await page.request.get(asset);
    expect(response.status(), asset).toBe(200);
    expect(response.headers()["content-type"], asset).toMatch(/javascript|css/);
  }

  // Client-side routes fall back to the app shell (nginx `try_files` parity).
  const deepLink = await page.request.get("/dashboard/NVDA");
  expect(deepLink.status()).toBe(200);
  expect(await deepLink.text()).toContain('<div id="root">');

  await page.goto("/dashboard/NVDA");
  await expect(page.getByTestId("tile")).toHaveCount(8);
  await expect(page.getByTestId("holder-row")).toHaveCount(5);
  await expect(page.getByTestId("tile-source").first()).toHaveText("fixtures");
  await expect(page.getByTestId("freshness-quotes")).toBeVisible();
  await expect(page.getByTestId("disclaimer")).toContainText("not investment advice");

  await scanPage(page, "production build");

  expect(errors, "console errors in the production build").toEqual([]);
});
