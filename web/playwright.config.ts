import { defineConfig } from '@playwright/test'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const databasePath = join(
  tmpdir(),
  `tradingagents-playwright-${process.pid}-${Date.now()}`,
  'workspace.sqlite3',
)

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 8_000 },
  outputDir: 'test-results',
  reporter: [['list'], ['html', { open: 'never' }]],
  use: { baseURL: 'http://127.0.0.1:5175', trace: 'retain-on-failure' },
  webServer: [
    {
      command: `TRADINGAGENTS_WEB_DEMO=1 TRADINGAGENTS_WEB_DB_PATH=${databasePath} ../.venv/bin/python -m uvicorn tradingagents.web.app:app --host 127.0.0.1 --port 8010`,
      url: 'http://127.0.0.1:8010/api/health',
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: 'VITE_API_TARGET=http://127.0.0.1:8010 npm run dev -- --host 127.0.0.1 --port 5175',
      url: 'http://127.0.0.1:5175',
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
})
