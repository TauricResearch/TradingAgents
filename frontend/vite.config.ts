import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";
// vitest/config re-exports vite's defineConfig with the `test` field typed
import { defineConfig } from "vitest/config";

// Build lands inside the Python package (shipped via package-data) so one
// FastAPI app serves API + SPA from a single origin on :8600.
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: "prompt", // never silently swap a trading UI
      manifest: {
        name: "TradingAgents Pro",
        short_name: "TA Pro",
        description: "Explainable multi-agent trading terminal",
        theme_color: "#0d1117",
        background_color: "#0d1117",
        display: "standalone",
        icons: [
          { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
          {
            src: "/icons/icon-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "any maskable",
          },
        ],
      },
      workbox: {
        // Precache the shell only. Trading data must NEVER be cache-served:
        // a stale kill-switch state is a safety bug, so /api/* stays
        // NetworkOnly except immutable historical bars.
        globPatterns: ["**/*.{js,css,html,woff2,png,svg}"],
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api/, /^\/legacy/, /^\/healthz/],
        runtimeCaching: [
          {
            urlPattern: /\/api\/bars/,
            handler: "NetworkFirst",
            options: {
              cacheName: "bars",
              expiration: { maxEntries: 32, maxAgeSeconds: 300 },
              cacheableResponse: { statuses: [200] },
            },
          },
          { urlPattern: /\/api\//, handler: "NetworkOnly" },
        ],
      },
    }),
  ],
  build: {
    outDir: "../tradingagents/pro/dashboard/static",
    emptyOutDir: true, // intentional: the dir belongs to this build
    sourcemap: "hidden", // maps for CI artifacts, never shipped in the wheel
    rollupOptions: {
      output: {
        manualChunks: {
          charts: ["lightweight-charts"],
          grid: ["react-grid-layout"],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        // override when the demo backend runs on a non-default port
        target: process.env.PRO_API_TARGET ?? "http://127.0.0.1:8600",
        changeOrigin: false,
      },
    },
  },
  resolve: {
    alias: { "@": "/src" },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["src/test/setup.ts"],
    css: false,
    // e2e/ belongs to Playwright; vitest's default glob would ingest it
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
