import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import fs from "fs";
import path from "path";

function versionPlugin() {
  return {
    name: "version-inject",
    buildStart() {
      const versionFile = path.resolve(__dirname, "../../VERSION");
      const version = fs.readFileSync(versionFile, "utf-8").trim();
      const outPath = path.resolve(__dirname, "src/version.ts");
      fs.writeFileSync(outPath, `export const VERSION = ${JSON.stringify(version)};\n`);
    },
  };
}

export default defineConfig({
  plugins: [react(), versionPlugin()],
  server: {
    port: 5173,
    proxy: {
      // Pin to 127.0.0.1 (not `localhost`) so Vite's http-proxy can't
      // resolve to ::1 (IPv6) on hosts where `localhost` is dual-stack
      // and the backend (uvicorn, bound to 127.0.0.1) is not — that
      // mismatch surfaced as ECONNREFUSED in the Vite log.
      "/api": "http://127.0.0.1:8000",
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/__tests__/setup.ts"],
    exclude: ["node_modules", "dist", "e2e/**"],
  },
});
