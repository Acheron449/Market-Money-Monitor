import { expect, test, type Page } from "@playwright/test";

interface FocusState {
  testId: string | null;
  tag: string;
  outlineStyle: string;
  outlineWidth: number;
}

async function focusState(page: Page): Promise<FocusState | null> {
  return page.evaluate(() => {
    const element = document.activeElement as HTMLElement | null;
    if (!element || element === document.body) return null;
    const style = getComputedStyle(element);
    return {
      testId: element.getAttribute("data-testid"),
      tag: element.tagName.toLowerCase(),
      outlineStyle: style.outlineStyle,
      outlineWidth: Number.parseFloat(style.outlineWidth || "0"),
    };
  });
}

/** Advance the tab order with real Tab presses until the predicate matches. */
async function tabTo(
  page: Page,
  matches: (state: FocusState) => boolean,
  maxStops = 120,
): Promise<FocusState> {
  for (let stop = 0; stop < maxStops; stop += 1) {
    await page.keyboard.press("Tab");
    const state = await focusState(page);
    if (state && matches(state)) return state;
  }
  throw new Error("the tab order never reached the expected control");
}

test("tab order shows a visible focus ring on every stop", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("tile")).toHaveCount(8);
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());

  const seen: FocusState[] = [];
  for (let stop = 0; stop < 12; stop += 1) {
    await page.keyboard.press("Tab");
    const state = await focusState(page);
    if (!state) break;
    seen.push(state);
    expect(state.outlineStyle, `${state.tag} focus ring`).not.toBe("none");
    expect(state.outlineWidth, `${state.tag} focus ring width`).toBeGreaterThanOrEqual(2);
  }

  // Header actions, the exclusion checkbox and the signal tiles are all reachable.
  expect(seen.length).toBeGreaterThanOrEqual(10);
  expect(seen.some((state) => state.testId === "tile")).toBe(true);
  expect(seen.some((state) => state.testId === "exclude-10b5-1")).toBe(true);
});

test("tiles, tape filters and panels are operable from the keyboard", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("tile")).toHaveCount(8);

  const tile = await tabTo(page, (state) => state.testId === "tile");
  expect(tile.outlineWidth).toBeGreaterThanOrEqual(2);
  const ticker = await page.evaluate(() =>
    document.activeElement?.getAttribute("data-ticker"),
  );
  expect(ticker).toBeTruthy();

  await page.keyboard.press("Enter");
  await expect(page.locator(`[data-testid="tile"][data-ticker="${ticker}"]`)).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByTestId("tape-ticker")).toHaveText(ticker ?? "");

  // Tape filters are plain buttons, so Enter toggles them.
  const buys = page.getByRole("button", { name: "Buys only" });
  await tabTo(page, (state) => state.tag === "button");
  await buys.focus();
  await page.keyboard.press("Enter");
  await expect(buys).toHaveAttribute("aria-pressed", "true");
  const actions = await page.getByTestId("tape-row").evaluateAll((rows) =>
    rows.map((row) => row.getAttribute("data-action")),
  );
  expect(actions.length).toBeGreaterThan(0);
  expect(new Set(actions)).toEqual(new Set(["buy"]));
  expect((await focusState(page))?.outlineWidth).toBeGreaterThanOrEqual(2);

  // Space toggles the 10b5-1 exclusion, which issues a real API request.
  const toggle = page.getByTestId("exclude-10b5-1");
  await tabTo(page, (state) => state.testId === "exclude-10b5-1");
  const filtered = page.waitForRequest(
    (request) => request.url().includes("/api/dashboard") && request.url().includes("exclude10b5_1=true"),
  );
  await page.keyboard.press("Space");
  await expect(toggle).toBeChecked();
  await filtered;

  // The watchlist editor opens from the keyboard and takes focus into its form.
  const edit = page.getByRole("button", { name: "Edit watchlist" });
  await edit.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("watchlist-editor")).toBeVisible();
  await expect(page.getByTestId("watchlist-row")).toHaveCount(8);

  await page.getByTestId("watchlist-add-input").focus();
  await expect(page.getByTestId("watchlist-add-input")).toBeFocused();
  const inEditor = await page.evaluate(() => {
    const editor = document.querySelector('[data-testid="watchlist-editor"]');
    return editor?.contains(document.activeElement) ?? false;
  });
  expect(inEditor).toBe(true);
});
