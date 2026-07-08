# TradingAgents Pro — Frontend

Vite + React 19 + TypeScript (strict) + Tailwind v4. Built assets land in
`../tradingagents/pro/dashboard/static/` and ship inside the Python
wheel; one FastAPI app serves API + SPA on :8600.

```bash
npm ci                 # install (Node 22, see .nvmrc)
npm run dev            # hot reload on :5173, /api proxied to :8600
npm run build          # typecheck + production build into the package
npm test               # vitest unit tests
npm run lint           # eslint
npm run e2e            # Playwright against the seeded demo server
npm run storybook      # component workshop (a11y addon, theme toolbar)
```

Layout: `src/app/` shell + safety chrome · `src/features/<module>/`
pages · `src/components/` reusable (Storybook-covered) ·
`src/lib/` api/zod/sse/binance/staleness/shortcuts · `src/stores/`
zustand (ui, ticker, layout).

Rules that keep this codebase honest:

- The UI **formats** numbers; it never computes trading quantities.
  Indicators come from `/api/bars/indicators` (deterministic engine).
- Direction always renders through `<DirectionBadge>` (glyph + word +
  color — never color alone).
- Every widget must express empty / degraded / error / locked states;
  no placeholder numbers, no faked liveness.
- `/api/**` is NetworkOnly in the service worker (except historical
  bars): a cached kill-switch state is a safety bug.
- The status strip and halt banner are not part of any layout grid.
