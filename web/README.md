# TradingAgents Dashboard

A web UI for running the multi-agent TradingAgents pipeline on a watchlist
of tickers and streaming every event in real time.

## Quick start (production-style)

```bash
# 1. install backend deps
uv sync

# 2. build the frontend
cd web/frontend
npm install
npm run build
cd ../..

# 3. start the dashboard
uv run uvicorn web.server.app:create_app --factory
# → http://localhost:8000
```

## Dev mode (hot reload)

```bash
# terminal 1: backend
uv run uvicorn web.server.app:create_app --factory --reload

# terminal 2: frontend
cd web/frontend
npm run dev
# → http://localhost:5173 (proxies /api and /ws to :8000)
```

## Tests

```bash
# backend
pytest web/server -v

# frontend
cd web/frontend
npx vitest run

# e2e (slow, requires a running server)
npx playwright test
```

## Configuration

Env vars: see `web/server/settings.py`. Most useful:

- `TRADINGAGENTS_DASHBOARD_PORT` (default 8000)
- `TRADINGAGENTS_DASHBOARD_MAX_CONCURRENT` (default 3)
- `TRADINGAGENTS_DASHBOARD_PRICE_POLL_S` (default 15)
- `TRADINGAGENTS_DASHBOARD_DB` (default `~/.tradingagents/dashboard.db`)

## Manual checklist

See `web/frontend/e2e/README.md`.
