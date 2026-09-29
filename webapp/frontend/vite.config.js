import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` proxies /api to the FastAPI backend (run separately with
// `uvicorn webapp.backend.main:app --reload`) so the dev server and the API
// share an origin the same way the production build does once FastAPI
// serves this app's built `dist/` directly.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
