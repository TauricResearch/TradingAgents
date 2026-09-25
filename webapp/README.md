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

Any standard ASGI host works (Fly.io, Render, a small VPS behind Caddy/
Nginx, etc.). Point it at a persistent volume for the SQLite file and the
`tradingagents` cache/results directories (`TRADINGAGENTS_*_DIR` env vars,
see the top-level `.env.example`), and set real LLM + Stripe keys as
secrets rather than in `.env`.
