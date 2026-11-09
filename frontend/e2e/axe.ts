import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

/**
 * AC-07: scan the live document with axe, using the WCAG 2.1 A/AA rule set.
 * Serious and critical findings fail the suite; no rule is disabled and no
 * element is excluded, so a regression in any state is a build break.
 */
export async function scanPage(page: Page, state: string): Promise<void> {
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
