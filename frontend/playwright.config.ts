import { defineConfig, devices } from "@playwright/test";

/** E2E against the seeded demo server (real pipeline/backtest code, fake
 * LLM + synthetic bars) with auth enabled — the same fixture the Python
 * suite trusts. Run from repo root context: the demo script imports
 * test fakes. */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  // one worker: both projects share a single server + prefs store, and
  // watchlist/saved-view tests do read-modify-write over that state
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://127.0.0.1:8600",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    // Pixel 5 emulation is chromium-based: one browser install covers both
    { name: "mobile", use: { ...devices["Pixel 5"] } },
  ],
  webServer: {
    // TRADINGAGENTS_PRO_DATA in a temp dir: prefs/watchlist tests must
    // never touch the operator's real ~/.tradingagents state
    command:
      'cd .. && PRO_DASHBOARD_TOKEN=e2e-token TRADINGAGENTS_PRO_DATA="$(mktemp -d)" ' +
      `${process.env.PRO_PYTHON ?? "python"} scripts/pro_dashboard_demo.py 8600`,
    url: "http://127.0.0.1:8600/healthz",
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
