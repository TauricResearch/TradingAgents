import { test, expect } from "@playwright/test";

test("full run: add ticker, run analysis, see decision", async ({ page }) => {
  await page.goto("/");
  await page.getByText("+ Add ticker").click();
  await page.getByPlaceholder("Ticker symbol").fill("NVDA");
  await page.keyboard.press("Enter");

  // Focused should now be NVDA
  await expect(page.getByRole("heading", { name: "NVDA" })).toBeVisible();

  // Run analysis (uses real TradingAgentsGraph with a stubbed propagate in the test env)
  await page.getByRole("button", { name: "Run analysis" }).click();

  // Wait for decision panel
  await expect(page.getByText(/DECISION/)).toBeVisible({ timeout: 120_000 });
});
