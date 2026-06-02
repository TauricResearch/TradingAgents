import { defineConfig } from "@playwright/test";

// Note: The Python backend is launched via `uv run` rather than `python -m uvicorn`
// because this project is uv-managed and there is no `python` on PATH in our
// dev environment. `uv run` resolves the venv and dependencies from the project
// root (one level above `web/frontend/`).
export default defineConfig({
  testDir: "./e2e",
  webServer: [
    {
      command:
        "cd ../.. && uv run uvicorn web.server.app:create_app --factory --port 8000",
      port: 8000,
      reuseExistingServer: true,
      timeout: 30_000,
    },
    {
      command: "npm run dev",
      port: 5173,
      reuseExistingServer: true,
      timeout: 30_000,
    },
  ],
  use: { baseURL: "http://localhost:5173" },
});
