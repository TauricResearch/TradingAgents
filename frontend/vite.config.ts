import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build straight into the tracked Python package so the installed wheel
// serves the SPA without Node at runtime. `base: "/"` keeps hashed asset URLs
// absolute so the SPA fallback route works at any client path.
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: {
    outDir: "../tradingagents/web/static",
    emptyOutDir: true,
    assetsDir: "assets",
    sourcemap: false,
  },
});