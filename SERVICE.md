# trading-agents-service

> FastAPI service wrapper around the upstream [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) library, deployed on Railway. Part of the [Lyceum Fund](https://linear.app/two-trees-digital/issue/TT-182) app.

This file documents **the Two Trees fork layer**. The original TradingAgents library code lives unchanged in `tradingagents/` and `cli/` at the repo root — see `README.md` for upstream docs.

## Architecture

```
┌─────────────────────────────────┐
│ lyceum-fund (Node, on Vercel)   │  ← user signs in, enters ticker
│  apps/dashboard, apps/api,      │
│  apps/worker                    │
└─────────┬───────────────────────┘
          │ HMAC-signed HTTP
          ▼
┌─────────────────────────────────┐
│ trading-agents-service          │  ← this repo
│ (Python, FastAPI, on Railway)   │
│                                 │
│  app/        ← Two Trees layer  │
│   ├─ main.py        FastAPI     │
│   ├─ config.py      env loader  │
│   └─ observability  Sentry      │
│                                 │
│  tradingagents/  ← upstream lib │
│  cli/            ← upstream     │
└─────────┬───────────────────────┘
          │ shared
          ▼
┌──────────────┐  ┌──────────────┐
│ Neon Postgres │  │ Upstash Redis│
│   (shared)    │  │  (shared)    │
└───────────────┘  └──────────────┘
```

Shared infrastructure with the `lyceum-fund` Node app:
- **Neon Postgres** — Python's `DATABASE_URL` = Node's `DIRECT_URL`. Python writes `runs`/`decisions`/`agent_reports`; Node owns `users`/`UserBudget`/`WatchlistItem`.
- **Upstash Redis** — Python publishes to `run:<runId>` channels; Node's dashboard subscribes via browser SSE.

## Two Trees layer (app/)

Code we own and maintain. Treated as future `python-temp-pro` template files — no trading-specific shortcuts.

| File | Purpose |
|---|---|
| `app/config.py` | pydantic-settings env loader. Required: DATABASE_URL, REDIS_URL, OPENAI_API_KEY, HMAC_SHARED_SECRET. |
| `app/observability.py` | Sentry init with FastAPI/Starlette/SQLAlchemy integrations. Tags events with `app:<APP_SLUG>` so the shared `two-trees-shared-python` Sentry project is per-app filterable. |
| `app/main.py` | FastAPI entrypoint. `/health` + `/ready` for now. `/analyze` + `/stream/{run_id}` land in [TT-182c](https://linear.app/two-trees-digital/issue/TT-182). |

## Upstream layer (tradingagents/, cli/, main.py, test.py, etc.)

Code from TauricResearch's TradingAgents. We:
- **Don't modify it** unless absolutely necessary (e.g., TT-182c will swap file-based memory for Postgres).
- **Keep it in sync** with upstream periodically. The fork has the original `main` branch + our `main`. To pull upstream changes:
  ```bash
  git remote add upstream git@github.com:TauricResearch/TradingAgents.git
  git fetch upstream
  git merge upstream/main
  # resolve any conflicts (likely in Dockerfile / pyproject.toml — they're known forked files)
  ```
- **Pinned version**: TBD in [TT-182e](https://linear.app/two-trees-digital/issue/TT-182). Don't auto-bump.

## Env vars

See `.env.example` for the full list. Two groups:

**Service-wrapper layer (required by `app/config.py`)**:

| Var | Required | Description |
|---|---|---|
| `DATABASE_URL` | yes | Neon pooled URL |
| `REDIS_URL` | yes | Upstash redis URL |
| `OPENAI_API_KEY` | yes | LLM provider |
| `HMAC_SHARED_SECRET` | yes | Service-to-service auth |
| `DIRECT_URL` | no | Neon direct URL (for Alembic in TT-182b) |
| `SENTRY_DSN` | no | If unset, no Sentry events |
| `APP_SLUG` | no | Sentry tag — defaults to `"unknown"` |
| `NODE_ENV` | no | `production` on Railway |
| `PORT` | no | Railway injects |

**Upstream library**: see `.env.example` lines below the wrapper section. The TradingAgents code reads its own `TRADINGAGENTS_*` env vars + LLM provider keys directly.

## Local dev

```bash
# 1. Install deps (uses uv per pyproject.toml's uv.lock)
uv sync

# 2. Copy env template + fill in
cp .env.example .env
# Edit .env — at minimum set DATABASE_URL, REDIS_URL, OPENAI_API_KEY, HMAC_SHARED_SECRET

# 3. Run the service
uvicorn app.main:app --reload --port 8000

# 4. Verify
curl http://localhost:8000/health
curl http://localhost:8000/ready  # 200 if DB + Redis reachable, 503 otherwise
```

## Deploy

Railway auto-deploys on push to `main`. Config in `railway.json`:
- Dockerfile build
- Healthcheck `/health` (30s timeout)
- Restart on failure (max 5 retries)

The `.github/workflows/deploy-railway.yml` workflow runs a post-deploy `/health` smoke check. Set `API_URL` in repo Settings → Secrets to enable it.

## Phase status

| Phase | Status | Ticket |
|---|---|---|
| 182a — Scaffold + Railway deploy | this PR | [TT-281](https://linear.app/two-trees-digital/issue/TT-281) |
| 182b — SQLAlchemy + Alembic + HMAC auth | pending | [TT-282](https://linear.app/two-trees-digital/issue/TT-282) |
| 182c — Wrap TradingAgents (/analyze, SSE) | pending | [TT-283](https://linear.app/two-trees-digital/issue/TT-283) |
| 182d — Node-side UI + cost cap | pending | [TT-284](https://linear.app/two-trees-digital/issue/TT-284) |
| 182e — Integration + polish | pending | [TT-285](https://linear.app/two-trees-digital/issue/TT-285) |
