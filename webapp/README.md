# TradingAgents Web — SaaS layer

A FastAPI service (`backend/`) plus a React (Vite) frontend (`frontend/`)
that turns the `tradingagents` research pipeline into a product: signup, an
API key, a free monthly quota, and a Stripe-powered paid tier for unlimited
runs.

It only ever *generates research reports and a suggested decision label*. It
never places trades and is not financial advice (see the top-level README's
disclaimer) — this keeps the product in "research tool" territory instead of
"investment adviser" territory, which matters for licensing in most
jurisdictions.

## Monetization model

- **Free tier**: `TRADINGAGENTS_FREE_TIER_LIMIT` (default 5) analysis runs
  per user per calendar month, no card required.
- **Pro tier**: unlimited runs via a Stripe subscription. `POST
  /api/billing/checkout` returns a Stripe Checkout URL; the webhook at
  `POST /api/billing/webhook` flips the user's plan on
  `checkout.session.completed` / subscription cancellation.
- Natural extensions once there's traction: per-seat team plans, a
  pay-per-report credit pack for occasional users, or a higher-priced tier
  that runs the deeper/more expensive model config (`deep_think_llm`).

## Cost control: cross-user result cache

A completed `(ticker, trade_date)` analysis is reused across *all* users for
`TRADINGAGENTS_CACHE_TTL_HOURS` (default 24, see `.env.example`) instead of
re-running the LLM pipeline. A historical trade_date's result is effectively
static, so if ten users ask for the same hot ticker today, only the first
run costs LLM tokens — the rest get an instant result and don't spend their
monthly quota. `POST /api/analyze` reports `"cached": true/false`, and the
frontend's "recent prints" list shows which runs were served from cache.

## Frontend architecture (`webapp/frontend/`)

A Vite + React app (functional components, hooks only — no class
components), built as a fully static bundle that FastAPI serves directly:

- `src/hooks/useTradingApi.js` — the single point of contact with the API.
  Owns the API key (with an opt-in "remember on this device" persisted to
  `localStorage`) and exposes one memoized async function per endpoint.
  Components keep their own loading/error state around these calls.
- `src/hooks/useJobPolling.js` — polls `GET /api/jobs/{id}` every 4s while a
  job is `queued`/`running`, with proper cleanup (a cancelled flag + cleared
  timeout) on unmount or when the job id changes, so a stale poll can never
  set state after the component has moved on.
- `src/components/` — `SignupPanel`, `AccountPanel`, `AnalyzeForm`,
  `DecisionStamp` (the hero: a resolved decision renders as a market
  "print" — ticket id + UTC timestamp, not a generic result card),
  `ReportView`, `HistoryTape`, `ThemeToggle`.
- `src/styles/tokens.css` — the whole design system (colors, type scale,
  spacing, motion) as CSS custom properties, with a light/dark pair driven
  by both `prefers-color-scheme` and an explicit `ThemeToggle` override.

### Running it locally

Two processes: the FastAPI backend, and (for active frontend development)
the Vite dev server, which proxies `/api` to it.

```bash
# terminal 1 — backend, from the repo root
cp webapp/.env.example webapp/.env   # fill in your LLM provider key
export $(grep -v '^#' webapp/.env | xargs)
pip install -e ".[webapp]"
uvicorn webapp.backend.main:app --reload --port 8000

# terminal 2 — frontend, hot-reloading dev server
cd webapp/frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173 (Vite) during development — API calls are
proxied to the backend on :8000. For a production-shaped run, instead build
the frontend and let FastAPI serve it directly on one origin:

```bash
cd webapp/frontend && npm install && npm run build   # writes webapp/frontend/dist/
cd ../.. && uvicorn webapp.backend.main:app           # from the repo root
```

Then open http://127.0.0.1:8000. If `dist/` hasn't been built yet, the
backend still starts and the API still works — it just skips mounting the
UI and logs a reminder to run `npm run build`.

## API summary

| Endpoint | Auth | Purpose |
|---|---|---|
| `POST /api/signup` | none | Register an email, get back an API key |
| `GET /api/me` | API key | Plan + usage this month |
| `POST /api/analyze` | API key | Queue an analysis run `{ticker, trade_date?}` → `{job_id}` |
| `GET /api/jobs/{id}` | API key | Poll job status/result |
| `GET /api/jobs` | API key | Recent job history |
| `POST /api/billing/checkout` | API key | Get a Stripe Checkout URL for the Pro plan |
| `POST /api/billing/webhook` | Stripe signature | Stripe calls this to report subscription changes |

## What's intentionally out of scope for this MVP

- **No trade execution.** Wiring a broker (e.g. Alpaca) is a much larger,
  much riskier follow-on step (real money, real compliance obligations) and
  should be a deliberate later decision, not bundled into the research
  product.
- **No user auth beyond a bearer API key** (no passwords, OAuth, or email
  verification yet) — fine for an early access / waitlist launch, worth
  hardening before a public launch.
- **SQLite, single process.** Swap for Postgres + a real task queue
  (e.g. Celery/RQ) once concurrent usage outgrows a handful of users.
- **Rate limiting is monthly-count only**, not per-minute abuse protection —
  add that (e.g. via a reverse proxy) before opening signups publicly.
- **No JS unit tests yet** (Vitest + React Testing Library would be the
  natural fit). The frontend is currently verified via ESLint, a production
  build in CI, and manual/Playwright checks against the real backend; the
  backend's own behavior (quota, caching, billing) is covered by
  `tests/test_webapp.py`.

## Deploying

### Docker

```bash
# from the repo root
cp webapp/.env.example webapp/.env   # fill in LLM provider key + Stripe keys
cp .env.example .env                 # only needed if `tradingagents` (the CLI service) is used too
docker compose --profile webapp up --build webapp
```

This builds `webapp/Dockerfile` (a second image alongside the existing
top-level `Dockerfile` for the CLI). It's a three-stage build: a Node stage
runs `npm ci && npm run build` for the React app, a Python stage installs
the backend, and the final image copies both — `uvicorn` (not the
`tradingagents` CLI entrypoint) serves the API and the built `dist/` on
`http://localhost:8000`. It shares the `tradingagents_data` volume with the
CLI service, so the webapp's SQLite file and the `tradingagents` cache/
results/memory directories persist across restarts.

Any standard container host works from there (Fly.io, Render, a small VPS
behind Caddy/Nginx, etc.) — point `docker build -f webapp/Dockerfile .` at
it and set real LLM + Stripe keys as platform secrets rather than a
committed `.env`.

### Without Docker

See "Running it locally" above; the same `uvicorn webapp.backend.main:app`
command works in production behind a process manager (systemd, supervisor)
and a reverse proxy for TLS.
