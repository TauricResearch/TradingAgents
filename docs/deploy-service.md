  Yes — Pulse-TradingAgents is already built to run as a Pulse microservice. The repo ships a FastAPI app (api/main.py) on port 8000, routes under
  /signals-ms/*, plus Docker and docker-compose. What’s missing is production wiring (registry, CI/CD, nginx, secrets) — the same pattern as
  pulse-feed-service and pulse-academy-backend.

  ────────────────────────────────────────

  What it is today

  ┌──────────────────────────────┬────────────────────────────────────────────────────────────────────────┐
  │ Piece                        │ Status                                                                 │
  ├──────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
  │ HTTP API (FastAPI + Uvicorn) │ Ready — /signals-ms/signals, /health, SSE /stream, etc.                │
  ├──────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
  │ Background scheduler         │ Runs TradingAgents on watchlist (default every 24h per ticker)         │
  ├──────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
  │ Storage                      │ SQLite (~/.tradingagents/db/signals.db) + Redis (SSE pub/sub)          │
  ├──────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
  │ Auth                         │ JWT (PULSE_JWT_SECRET) or X-User-Id / X-User-Tier from nginx           │
  ├──────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
  │ Docker                       │ Dockerfile + docker-compose.yml                                        │
  ├──────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
  │ GitHub deploy CI             │ Not yet (unlike feed/auth/academy)                                     │
  ├──────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
  │ Frontend UI                  │ Pending (pulse-frontend → NEXT_PUBLIC_PULSE_API_URL + /signals-ms/...) │
  └──────────────────────────────┴────────────────────────────────────────────────────────────────────────┘

  It fits the Pulse map in ACTIVE_REPOS.md:

  pulse-auth-service (JWT + tier) → Pulse-TradingAgents (signals-ms) → pulse-frontend

  ────────────────────────────────────────

  How it would sit on your server

  Same model as academy/feed: Docker on the host, bound to localhost, nginx on 443.

  mermaid flowchart

  flowchart LR
    user[Browser / pulse-frontend]
    nginx[Nginx staging-backend.pulsenow.io]
    signals[pulse-trading-signals :8002]
    redis[pulse-redis-signals :6379 internal]
    gemini[Google Gemini API]
    user -->|HTTPS /signals-ms/*| nginx
    nginx -->|127.0.0.1:8002| signals
    signals --> redis
    signals --> gemini

  Suggested port: 127.0.0.1:8002:8000 (8000/8001 often used by feed/auth on staging).

  Nginx (add to existing staging-backend site):

  location /signals-ms/ {
      proxy_pass http://127.0.0.1:8002;
      proxy_http_version 1.1;
      proxy_set_header Host $host;
      proxy_set_header X-Real-IP $remote_addr;
      # SSE needs longer timeouts
      proxy_read_timeout 3600s;
      proxy_buffering off;
  }

  Frontend then calls:
  https://staging-backend.pulsenow.io/signals-ms/signals (same base as /feed-ms, /auth-ms).

  ────────────────────────────────────────

  Minimal server deploy (manual, today)

  On the server (e.g. /home/jason/pulse-trading-agents or similar):

  1. .env (never commit keys):

  GOOGLE_API_KEY=...
  TRADINGAGENTS_LLM_PROVIDER=google
  TRADINGAGENTS_DEEP_THINK_LLM=gemini-2.5-flash
  TRADINGAGENTS_QUICK_THINK_LLM=gemini-2.5-flash
  REDIS_URL=redis://pulse-redis-signals:6379/0
  # Must match pulse-auth-service JWT signing secret
  PULSE_JWT_SECRET=<same as auth-ms>
  JWT_ALGORITHM=HS256
  FREE_TIER_QUOTA_LIMIT=3
  TRADING_SIGNALS_CADENCE_HOURS=24

  2. Production-oriented compose (tweak the repo file):

  • Bind API to 127.0.0.1:8002:8000 (not 0.0.0.0:8000)
  • Don’t expose Redis on host port 6379 (conflicts with academy/other stacks)
  • Volume for SQLite: tradingagents_data:/home/appuser/.tradingagents
  • restart: unless-stopped
  • Optional: join external pulse-network if other containers need internal access

  3. Start:

  docker compose up -d --build
  curl -s http://127.0.0.1:8002/signals-ms/health

  4. Smoke test:

  curl -H "Authorization: Bearer <jwt>" \
    https://staging-backend.pulsenow.io/signals-ms/signals

  ────────────────────────────────────────

  Requirements and caveats

  1. Gemini API key — agent runs call Google; billing/quota on that key.
  2. JWT secret alignment — PULSE_JWT_SECRET must match pulse-auth-service, or nginx must pass X-User-Id / X-User-Tier.
  3. Resources — heavier than feed-ms (multi-agent LLM). Plan ≥2 GB RAM for the API container; agent runs can take minutes per ticker.
  4. Separate Redis — use a dedicated Redis in this compose stack (don’t share academy Redis unless you namespace DB index carefully).
  5. SQLite — fine for v1; back up the volume. Postgres migration is optional later.
  6. Security — tighten CORS in api/main.py from * to Pulse domains before prod.
  7. env.example in repo — contains what looks like a real API key; rotate if that was ever committed.

  ────────────────────────────────────────

  What “proper Pulse deploy” would add (like feed-service)

  ┌──────┬────────────────────────────────────────────────────────────────────────────────────────┐
  │ Step │ Action                                                                                 │
  ├──────┼────────────────────────────────────────────────────────────────────────────────────────┤
  │ 1    │ Production docker-compose.yml (localhost bind, no public Redis)                        │
  ├──────┼────────────────────────────────────────────────────────────────────────────────────────┤
  │ 2    │ GitHub Actions: build → registry.pulsenow.io/pulse/trading-signals:latest → SSH deploy │
  ├──────┼────────────────────────────────────────────────────────────────────────────────────────┤
  │ 3    │ Server .env + DEPLOY_PATH secret                                                       │
  ├──────┼────────────────────────────────────────────────────────────────────────────────────────┤
  │ 4    │ Nginx /signals-ms/ block                                                               │
  ├──────┼────────────────────────────────────────────────────────────────────────────────────────┤
  │ 5    │ Health monitoring on /signals-ms/health                                                │
  ├──────┼────────────────────────────────────────────────────────────────────────────────────────┤
  │ 6    │ Frontend env + Trading Signals tab (still pending)                                     │
  └──────┴────────────────────────────────────────────────────────────────────────────────────────┘

  ────────────────────────────────────────

  Bottom line

  Yes, it’s deployable as a Pulse service today with Docker + nginx. The app side is largely done; the gap is ops: production compose, registry/CI, nginx
  route, shared JWT secret, and frontend integration.

  If you want to proceed, sensible order:

  1. Manual deploy on staging (validate health + one /generate run)
  2. Add CI/CD mirroring pulse-feed-service
  3. Wire nginx + frontend

  Tell me which you prefer — manual staging recipe, full CI/CD scaffold in the repo, or nginx config for your exact server path — and I can implement that
   next.
