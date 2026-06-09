import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Dev server proxies /api to the FastAPI backend on :8502 so the SPA and API
// share an origin (cookies work). In production FastAPI serves the built dist.
export default defineConfig({
  plugins: [vue()],
  server: {
    host: true, // expose the dev server on the LAN (0.0.0.0), not just localhost
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8502', changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
  },
})
