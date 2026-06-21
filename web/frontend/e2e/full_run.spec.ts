import { test, expect } from "@playwright/test";

async function clearWatchlist(apiBase: string) {
  try {
    const response = await fetch(`${apiBase}/api/watchlist`);
    const tickers = await response.json();
    for (const ticker of tickers) {
      await fetch(`${apiBase}/api/watchlist/${ticker.ticker}`, { method: "DELETE" });
    }
  } catch (e) {
    console.log("Failed to clear watchlist:", e);
  }
}

async function addTickerViaApi(apiBase: string, ticker: string) {
  try {
    await fetch(`${apiBase}/api/watchlist`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticker, company_name: "", exchange: "" }),
    });
  } catch (e) {
    console.log("Failed to add ticker:", e);
  }
}

test("full run: add ticker, run analysis, see decision", async ({ page }) => {
  const apiBase = "http://localhost:8000";

  // Clear watchlist and add NVDA via API
  await clearWatchlist(apiBase);
  await addTickerViaApi(apiBase, "NVDA");

  await page.goto("/");

  // Wait for the app to load and show NVDA in watchlist
  await expect(page.getByRole("heading", { name: "NVDA" })).toBeVisible({ timeout: 30000 });

  // Run analysis (uses real TradingAgentsGraph with a stubbed propagate in the test env)
  await page.getByRole("button", { name: "Run analysis" }).click();

  // Wait for decision panel
  await expect(page.getByText(/DECISION/)).toBeVisible({ timeout: 120_000 });
});
