# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: full_run.spec.ts >> full run: add ticker, run analysis, see decision
- Location: e2e\full_run.spec.ts:27:1

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByText(/DECISION/)
Expected: visible
Timeout: 120000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 120000ms
  - waiting for getByText(/DECISION/)

```

```yaml
- complementary:
  - text: Watchlist
  - button "Default"
  - text: "1"
  - img
  - textbox "Search ticker…"
  - button "Add group":
    - img
    - text: Add group
  - button "Drag NVDA to reorder NVDA 50% $210.69 — +2.95% Remove NVDA from watchlist":
    - img
    - text: NVDA 50% $210.69 — +2.95%
    - button "Remove NVDA from watchlist": ×
- main:
  - heading "TradingAgents" [level=1]
  - text: "Loaded models: Deep: MiniMax-M3 · Quick: MiniMax-M3"
  - button "Settings":
    - img
  - button "Past Runs"
  - button "Agent"
  - button "🔭 Observatory"
  - button "History"
  - heading "NVDA" [level=2]
  - text: 1/3 agents
  - img
  - text: +2.95%
  - paragraph: $210.69 · USD
  - button "Latest (live)":
    - img
    - text: Latest (live)
    - img
  - button "Running 1m 59s" [disabled]:
    - img
    - text: Running 1m 59s
  - button "Cancel"
  - text: 📊 Analyst Team 1m 6s 1/4
  - button "Market Analyst":
    - img
    - text: Market Analyst
  - button "Sentiment Analyst"
  - button "News Analyst"
  - button "Fundamentals Analyst"
  - text: 🔬 Research Team 0/3
  - button "Bull Researcher"
  - button "Bear Researcher"
  - button "Research Manager"
  - text: 💼 Trading Team 0/1
  - button "Trader"
  - text: ⚠️ Risk Management 0/3
  - button "Aggressive Analyst"
  - button "Conservative Analyst"
  - button "Neutral Analyst"
  - text: 📋 Portfolio Mgmt 0/1
  - button "Portfolio Manager"
  - text: 1 / 12 agents LLM 5 tools 0 elapsed 01:54
  - button "Event Stream"
  - button "LLM Trace"
  - text: "Event Stream 15 events 5:44:07 AMrun_started 5:44:56 AMthinking 5:45:00 AManalyst_started: Market Analyst 5:45:00 AManalyst_completed: market — completed 5:45:00 AManalyst_started: tools_market 5:45:00 AMthinking 5:45:10 AManalyst_started: Market Analyst 5:45:10 AManalyst_completed: market — completed 5:45:10 AManalyst_started: tools_market 5:45:10 AMthinking 5:45:49 AMthinking 5:45:49 AManalyst_started: Market Analyst 5:45:49 AManalyst_completed: market — completed 5:45:49 AManalyst_started: Msg Clear Market 5:46:01 AMthinking 1 / 3 agents LLM 5 tools 0 elapsed 1m 54s"
- dialog "Background past runs":
  - banner:
    - img
    - heading "Background Past Runs" [level=2]
    - button "Close":
      - img
  - group:
    - img
    - text: New job Ticker
    - combobox "Ticker":
      - option "NVDA" [selected]
      - option "Custom ticker…"
    - text: From
    - textbox "From": 2026-05-22
    - text: To
    - textbox "To": 2026-06-21
    - text: Every
    - combobox "Every":
      - option "1d" [selected]
      - option "1w"
      - option "2w"
      - option "1mo"
    - text: Parallel
    - combobox "Parallel":
      - option "1" [selected]
      - option "2"
      - option "4"
    - button "Start"
  - group:
    - img
    - text: Past jobs (last 10)
```

# Test source

```ts
  1  | import { test, expect } from "@playwright/test";
  2  | 
  3  | async function clearWatchlist(apiBase: string) {
  4  |   try {
  5  |     const response = await fetch(`${apiBase}/api/watchlist`);
  6  |     const tickers = await response.json();
  7  |     for (const ticker of tickers) {
  8  |       await fetch(`${apiBase}/api/watchlist/${ticker.ticker}`, { method: "DELETE" });
  9  |     }
  10 |   } catch (e) {
  11 |     console.log("Failed to clear watchlist:", e);
  12 |   }
  13 | }
  14 | 
  15 | async function addTickerViaApi(apiBase: string, ticker: string) {
  16 |   try {
  17 |     await fetch(`${apiBase}/api/watchlist`, {
  18 |       method: "POST",
  19 |       headers: { "Content-Type": "application/json" },
  20 |       body: JSON.stringify({ ticker, company_name: "", exchange: "" }),
  21 |     });
  22 |   } catch (e) {
  23 |     console.log("Failed to add ticker:", e);
  24 |   }
  25 | }
  26 | 
  27 | test("full run: add ticker, run analysis, see decision", async ({ page }) => {
  28 |   const apiBase = "http://localhost:8000";
  29 | 
  30 |   // Clear watchlist and add NVDA via API
  31 |   await clearWatchlist(apiBase);
  32 |   await addTickerViaApi(apiBase, "NVDA");
  33 | 
  34 |   await page.goto("/");
  35 | 
  36 |   // Wait for the app to load and show NVDA in watchlist
  37 |   await expect(page.getByRole("heading", { name: "NVDA" })).toBeVisible({ timeout: 30000 });
  38 | 
  39 |   // Run analysis (uses real TradingAgentsGraph with a stubbed propagate in the test env)
  40 |   await page.getByRole("button", { name: "Run analysis" }).click();
  41 | 
  42 |   // Wait for decision panel
> 43 |   await expect(page.getByText(/DECISION/)).toBeVisible({ timeout: 120_000 });
     |                                            ^ Error: expect(locator).toBeVisible() failed
  44 | });
  45 | 
```