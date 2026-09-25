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

## Product surface

Beyond the core "analyze a ticker" loop, the app is a small multi-page
product:

- **Watchlist** (`GET/POST /api/watchlist`, `DELETE /api/watchlist/{ticker}`)
  — save tickers you check often; "Analyze" on a row jumps to the Dashboard
  with that ticker prefilled.
- **History** — the full run tape, filterable by ticker and status
  (`GET /api/jobs?ticker=&status=&limit=&offset=`), not just the last few.
- **Profile** — display name (`PATCH /api/me`), plan/usage/member-since, an
  "Upgrade to Pro" action, and self-service API key rotation
  (`POST /api/me/regenerate-key` — the old key stops working immediately,
  for "I think this leaked" moments), plus a device sign-out.
- **Live price chart** (`GET /api/chart/{ticker}?range=`) — a free closing-
  price line for whatever ticker is typed into the Analyze form, debounced
  and fetched straight from yfinance. It costs no LLM tokens and no quota
  (unlike `/api/analyze`, which runs the full agent pipeline): this is a
  quick "does this even look interesting" glance before spending a run,
  not a substitute for the analysis itself. The product's actual output
  stays a BUY/SELL/HOLD call with the agents' full reasoning — the chart
  is context around that decision, not a second product.
- **Preferred currency** (`PATCH /api/me {currency}`) — set on Profile,
  used across the platform to show a converted price alongside the live
  chart's USD figure (e.g. "$157.40 ≈ €144.81"), and as the default base
  on the Rates page below.
- **Exchange rates** (`GET /api/rates?base=`) — a free, live Xe-style
  board for a curated set of currencies (USD, EUR, GBP, JPY, AUD, CAD,
  CHF, CNY, INR, AED, SAR, EGP), fetched from yfinance FX tickers. Same
  free/no-quota reasoning as the price chart.
- **Landing page** (signed-out `/`) — a full marketing page: hero, "how
  it works", a feature grid, **Pricing** (Free vs. Pro, both reflecting
  real values — the actual `free_tier_monthly_limit()` and Stripe-backed
  upgrade, no invented numbers) and **FAQ** sections, and a closing CTA.

## Frontend architecture (`webapp/frontend/`)

A Vite + React app (functional components, hooks only — no class
components) with client-side routing (`react-router-dom`), built as a fully
static bundle that FastAPI serves directly:

- `src/context/AppContext.jsx` — holds the API client and the loaded
  account, shared across the navbar and every page (so e.g. renaming
  yourself on Profile updates the navbar's quota chip without plumbing
  props through the router).
- `src/hooks/useTradingApi.js` — the single point of contact with the API.
  Owns the API key (with an opt-in "remember on this device" persisted to
  `localStorage`) and exposes one memoized async function per endpoint.
  Components keep their own loading/error state around these calls.
- `src/hooks/useJobPolling.js` — polls `GET /api/jobs/{id}` every 4s while a
  job is `queued`/`running`, with proper cleanup (a cancelled flag + cleared
  timeout) on unmount or when the job id changes, so a stale poll can never
  set state after the component has moved on.
- `src/pages/` — `LandingPage` (signed-out marketing page: hero, "how it
  works", feature grid, pricing, FAQ, CTA band, all with scroll-reveal
  animation), `DashboardPage` (analyze + the decision print), `HistoryPage`,
  `WatchlistPage`, `ProfilePage` (display name, currency, key rotation),
  `ExchangeRatesPage` (the live rates board).
- `src/components/` — `Navbar` + `Logo` (an SVG mark, not a raster asset),
  `AuthModal` (sign up / sign in as a dialog, opened from the navbar's
  "Sign in"/"Get started" buttons or the landing page's CTAs — closes and
  routes to the Dashboard itself once a key is set, watching
  `api.apiKey`), `Avatar` + `ProfileMenu` (initials-on-a-color avatar;
  click opens a dropdown with account info, Profile/Watchlist links, sign
  out), `SignupPanel`, `SignInPanel`, `AnalyzeForm`, `PriceChart` (a free,
  debounced closing-price line for whatever ticker is typed — no LLM cost),
  `DecisionStamp` (the hero: a resolved decision renders as a market
  "print" — ticket id + UTC timestamp, not a generic result card),
  `ReportView`, `HistoryTape` (polls live every 12s — no manual refresh
  button), `QuotaBar`, `ThemeToggle` (icon-only, sun/moon), `Reveal` (a
  thin `IntersectionObserver` wrapper used for the landing page's
  scroll-in sections).
- `src/styles/tokens.css` — the whole design system (colors, type scale,
  spacing, motion, elevation) as CSS custom properties, with a light/dark
  pair driven by both `prefers-color-scheme` and an explicit `ThemeToggle`
  override. Every animation (hero blobs, the mockup float, scroll-reveal,
  the modal, the live-tape pulse) is neutralized under
  `prefers-reduced-motion: reduce`.

Because this is a client-side-routed single-page app, the backend can't
just serve static files at "/" (`GET /history` would 404 on a hard refresh
or a shared link — see `main.py`'s `serve_spa` catch-all route, which
serves built assets at `/assets/*` and falls back to `index.html` for
every other non-`/api` path).

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
| `GET /api/me` | API key | Plan, usage, display name, currency, member-since |
| `PATCH /api/me` | API key | Set `{display_name?, currency?}` — partial update, only provided fields change |
| `POST /api/me/regenerate-key` | API key | Rotate the API key (old one stops working immediately) |
| `POST /api/analyze` | API key | Queue an analysis run `{ticker, trade_date?}` → `{job_id}` |
| `GET /api/jobs/{id}` | API key | Poll job status/result |
| `GET /api/jobs` | API key | Job history, filterable by `?ticker=&status=&limit=&offset=` |
| `GET /api/chart/{ticker}` | API key | Free closing-price series, `?range=5d\|1mo\|3mo\|6mo\|1y\|5y` |
| `GET /api/rates` | API key | Free live exchange-rate board, `?base=USD` (see `rates.SUPPORTED_CURRENCIES`) |
| `GET /api/watchlist` | API key | List saved tickers |
| `POST /api/watchlist` | API key | Add `{ticker}` |
| `DELETE /api/watchlist/{ticker}` | API key | Remove a ticker |
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
