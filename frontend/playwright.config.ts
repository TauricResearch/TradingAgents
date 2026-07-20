import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  retries: 0,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:8771",
    trace: "on-first-retry",
  },
  webServer: {
    command: "rtk zsh -lic 'cd /Users/david/codespace/TradingAgents && python scripts/e2e_server.py'",
    port: 8771,
    reuseExistingServer: true,
    timeout: 60_000,
  },
});