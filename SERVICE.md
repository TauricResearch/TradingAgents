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
| `app/logging_config.py` | stdlib logging: JSON in prod (log-aggregator friendly), human-readable in dev. Sentry breadcrumbs auto-installed. |
| `app/db.py` | SQLAlchemy 2.x async engine + sessionmaker + `get_db` FastAPI dependency. Owns the `asyncpg_url()` URL normalizer that strips libpq-only query params (`sslmode`, `channel_binding`) that asyncpg rejects. |
| `app/models.py` | ORM models for Python-owned tables (`Run`, `Decision`, `AgentReport`). Prisma-owned tables (User, Role, App, etc.) are NOT modeled here — we never write to them and treat `user_id` columns as plain String FKs. |
| `app/auth.py` | HMAC-SHA256 signature middleware. Verifies `X-Signature` + `X-Timestamp` headers on every POST/PUT/PATCH/DELETE. ±5min skew window. Skips `/health`, `/ready`, FastAPI docs paths. |
| `app/services/pubsub.py` | Redis pub-sub helpers for live event streaming on `run:<run_id>` channels. Generic — no trading knowledge. |
| `app/services/stream_token.py` | HMAC-signed compact tokens for SSE auth. `mint(run_id)` + `verify(token, run_id)`. |
| `app/services/callbacks.py` | LangChain `AsyncCallbackHandler` that captures each agent's chain start/end → writes `agent_reports` rows + publishes to Redis. |
| `app/services/trading_agents_runner.py` | Trading-specific orchestrator. Wraps `TradingAgentsGraph` (TauricResearch upstream), drives DB state + pub-sub for the lifetime of a run. **Only app-specific service file** per the TT-182 template-discipline rule. |
| `app/routes/analyze.py` | `POST /analyze` — HMAC-auth'd. Creates run row, schedules FastAPI BackgroundTask. Returns 202. |
| `app/routes/stream.py` | `GET /stream/{run_id}?token=...` — SSE feed. Token query param verified server-side. |
| `app/main.py` | FastAPI entrypoint. Registers middleware + routers, configures logging + Sentry. `/health` + `/ready` defined inline. |

## Endpoints

### `POST /analyze` — kick off a TradingAgents run

Auth: HMAC headers (see HMAC contract section below).

Request body:
```json
{
  "runId":     "uuid-the-node-side-chose",
  "userId":    "prisma-user-id",
  "ticker":    "AAPL",
  "tradeDate": "2026-05-16"
}
```

Response 202:
```json
{ "runId": "...", "status": "pending" }
```

Idempotent — calling twice with the same `runId` returns the existing run's current status without spawning a duplicate analysis.

The actual TradingAgents pipeline runs in a FastAPI BackgroundTask after the response. State transitions visible via the `runs` table or via subscribing to the SSE stream.

### `GET /stream/{run_id}?token=<signed>` — live SSE feed

Auth: query-param HMAC-signed token. Browser `EventSource` can't send custom headers, so this auth pattern replaces HMAC headers for browser-initiated streams.

**Token format** (Node side mints; Python verifies):
```
<base64url(payload_json)>.<hex(hmac_sha256(payload_b64, HMAC_SHARED_SECRET))>
```
Payload: `{"runId": "<uuid>", "exp": <unix_seconds>}`. Default lifetime: 30 minutes.

**Wire format**: `text/event-stream`. Each event:
```
data: {"type": "agent_finished", "agent": "market_analyst", "content": "...", "timestamp": "..."}

```
(Note the trailing blank line — SSE record separator.)

**Event types**:
- `run_started` — analysis kicked off
- `agent_started` — `{agent, timestamp}` — one of TradingAgents' agents began
- `agent_finished` — `{agent, content, timestamp}` — agent's output, persisted to `agent_reports`
- `agent_error` — `{agent, error, timestamp}` — agent chain raised
- `run_complete` — `{decision, timestamp}` — final BUY/SELL/HOLD, persisted to `decisions`
- `run_error` — `{error, timestamp}` — pipeline failed

The stream closes with an `event: close` record when the runner publishes a DONE_SENTINEL on the Redis channel (always sent — success or failure).

## HMAC contract (Node → Python)

The Node-side worker (lyceum-fund/apps/worker) signs every request to this service:

```
X-Signature: sha256=<hex>
X-Timestamp: <unix-seconds>
```

Where `<hex>` is `HMAC-SHA256("{timestamp}.{body}", HMAC_SHARED_SECRET)`.

`HMAC_SHARED_SECRET` is the same value on both sides — set on Platform's Node-side Railway env AND this service's Railway env. Rotating it requires restarting both services.

Replay protection: requests with `X-Timestamp` more than 5 minutes off from server clock are rejected with 401.

## Migrations (Alembic)

```bash
# Run pending migrations against DATABASE_URL/DIRECT_URL
alembic upgrade head

# Create a new migration (autogenerate from model diff)
alembic revision --autogenerate -m "add new_column to runs"

# Roll back one revision
alembic downgrade -1
```

The `alembic/env.py` `include_name` filter restricts autogenerate to Python-owned tables (`runs`, `decisions`, `agent_reports`) — Alembic never tries to drop or alter Prisma-owned tables, even if their models existed in `Base.metadata`.

When adding a new Python-owned table:
1. Add the model to `app/models.py`
2. Add the table name to the `include_name` allowlist in `alembic/env.py`
3. `alembic revision --autogenerate -m "..."` → review the generated migration, edit if needed, commit
4. Deploy → Railway's pre-deploy command runs `alembic upgrade head` automatically

URL resolution: Alembic prefers `DIRECT_URL` (non-pooled) over `DATABASE_URL` (pooled). PgBouncer's transaction-pooling mode doesn't support DDL transactions or advisory locks, both of which Alembic needs.

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
| 182a — Scaffold + Railway deploy | ✅ done | [TT-281](https://linear.app/two-trees-digital/issue/TT-281) |
| 182b — SQLAlchemy + Alembic + HMAC auth | ✅ done | [TT-282](https://linear.app/two-trees-digital/issue/TT-282) |
| 182c — Wrap TradingAgents (/analyze, SSE) | this PR | [TT-283](https://linear.app/two-trees-digital/issue/TT-283) |
| 182d — Node-side UI + cost cap | pending | [TT-284](https://linear.app/two-trees-digital/issue/TT-284) |
| 182e — Integration + polish | pending | [TT-285](https://linear.app/two-trees-digital/issue/TT-285) |
| Long-term — Arq worker for /analyze | pending | [TT-286](https://linear.app/two-trees-digital/issue/TT-286) |
