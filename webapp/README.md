# TradingAgents Web — SaaS layer

A minimal FastAPI service and static frontend that turns the `tradingagents`
research pipeline into a product: signup, an API key, a free monthly quota,
and a Stripe-powered paid tier for unlimited runs.

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
frontend history table shows which runs were served from cache.

## Running it locally

```bash
cd webapp
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your LLM provider key + (optionally) Stripe keys
export $(grep -v '^#' .env | xargs)   # or use direnv/dotenv

# from the repo root, so `tradingagents` resolves and StaticFiles finds webapp/frontend
cd ..
pip install -e .
uvicorn webapp.backend.main:app --reload
```

Then open http://127.0.0.1:8000.

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

## Deploying

### Docker

```bash
# from the repo root
cp webapp/.env.example webapp/.env   # fill in LLM provider key + Stripe keys
cp .env.example .env                 # only needed if `tradingagents` (the CLI service) is used too
docker compose --profile webapp up --build webapp
```

This builds `webapp/Dockerfile` (a second image alongside the existing
top-level `Dockerfile` for the CLI — same base, but runs `uvicorn` instead
of the `tradingagents` CLI entrypoint) and serves the API + frontend on
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
