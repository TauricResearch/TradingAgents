# TradingAgents Pro — Production Deployment Guide

**Default posture: paper trading.** Every artifact in this repo ships with
live execution structurally disabled (Constraint 5). Going live is a
checklist of explicit sign-off events, not a config flag.

## Local (Docker Compose)

```bash
export OPENAI_API_KEY=...     # or your provider of choice
export FRED_API_KEY=...       # free
export PRO_DASHBOARD_TOKEN=$(openssl rand -hex 24)   # dashboard X-API-Key
docker compose -f deploy/docker-compose.pro.yml up --build
# dashboard: http://localhost:8600
# with the Qdrant memory backend:
docker compose -f deploy/docker-compose.pro.yml --profile qdrant up
```

## Kubernetes

```bash
docker build -f deploy/Dockerfile.pro -t <registry>/tradingagents-pro:<tag> .
docker push <registry>/tradingagents-pro:<tag>
kubectl create secret generic pro-keys -n tradingagents-pro \
  --from-literal=OPENAI_API_KEY=... --from-literal=FRED_API_KEY=...
kubectl apply -f deploy/k8s/pro.yaml   # pin your image tag in the manifest
```

Probes hit `/api/overview`; memory/audit JSONL files live on the `pro-data`
PVC. One replica by design — the service loop is single-writer over its
memory and audit files.

## Cloud Run + Firebase Hosting

Firebase Hosting can't run this app directly — it's a FastAPI backend (SSE,
single in-process worker by design) serving the built SPA, not a static
site. The supported pairing is **Firebase Hosting (TLS/CDN front door) →
Cloud Run**, running the same `deploy/Dockerfile.pro` image; Hosting
rewrites every path to Cloud Run (`firebase.json` at repo root), so the
FastAPI app keeps serving both the SPA and `/api/*` exactly as it does
today.

**Auth:** the `PRO_DASHBOARD_TOKEN` X-API-Key path always works (curl,
scripts, e2e, emergency access). Google sign-in activates on top of it when
BOTH of these are set on the Cloud Run service (fail closed — a project id
without an allowlist keeps Google sign-in disabled, and the SPA then shows
the token form instead):

- `PRO_FIREBASE_PROJECT_ID` — the Firebase project id (ID-token audience)
- `PRO_ALLOWED_EMAILS` — comma-separated Google account allowlist; any
  other Google account is rejected with 403 *after* authenticating
- `PRO_FIREBASE_WEB_CONFIG` — the public web-app config JSON
  (`firebase apps:sdkconfig WEB <appId>`); keep `authDomain` at the DEFAULT
  `<project>.firebaseapp.com` — the auto-provisioned OAuth client only
  whitelists that domain's `/__/auth/handler` redirect, so pointing
  `authDomain` at the `web.app` Hosting domain fails the Google popup with
  `Error 400: redirect_uri_mismatch` (verified live). The popup returns the
  result via postMessage, so the cross-domain handler is fine.

One-time: register a web app (`firebase apps:create web pro-dashboard`) and
enable the **Google** provider in the Firebase console (Authentication →
Sign-in method → Google → Enable — the console auto-provisions the OAuth
client; the admin API refuses without one). Token verification runs through
`google-auth` (already a locked dependency): signature against Google's
certs, audience = the project id, `email_verified`, then the allowlist.

**Hard boundary: this deployment is paper-mode only.** No Delta/live-venue
credentials are configured here, and none should be — live trading needs an
always-on host per the promotion checklist below, which a scale-to-zero
Cloud Run service structurally is not.

**Why `--max-instances=1`:** the single-writer invariant noted above for
Kubernetes applies here too — everything under `TRADINGAGENTS_PRO_DATA`
(`memory.jsonl`, `runs/` history, `dashboard_prefs.json`, `paper_state.json`,
the `KILL` latch, hash-chained `audit.jsonl`, `arming.json`) must never be
written by more than one instance at once. Capping concurrent instances at 1
enforces that; `--min-instances=0` is still fine alongside it and keeps the
service scale-to-zero between visits (the automatic hourly loop is disabled
via `PRO_LOOP_DISABLED=1` for this deployment — on-demand runs from the "Run
pipeline now" button still work as long as an LLM key secret is set).

**Prerequisites:**
- A Firebase project on the **Blaze (pay-as-you-go)** plan — Hosting's
  Cloud Run rewrite feature isn't available on the free Spark plan.
- Enable these GCP APIs on the project: `run.googleapis.com`,
  `artifactregistry.googleapis.com`, `cloudbuild.googleapis.com`,
  `secretmanager.googleapis.com`, `storage.googleapis.com`.
- `gcloud` CLI (`gcloud auth login`, `gcloud config set project <id>`) and
  `firebase-tools` (`npm install -g firebase-tools`, `firebase login`) —
  both interactive OAuth flows, run them yourself.

**One-time setup** (replace `$PROJECT_ID`/`$REGION`/`$BUCKET` throughout):

```bash
gcloud artifacts repositories create pro-dashboard \
  --repository-format=docker --location="$REGION"

gcloud storage buckets create "gs://$BUCKET" --location="$REGION"

# secret VALUES are typed interactively — never pasted into chat or committed
printf '%s' "$PRO_DASHBOARD_TOKEN" | gcloud secrets create pro-dashboard-token --data-file=-
printf '%s' "$DEEPSEEK_API_KEY"    | gcloud secrets create deepseek-api-key --data-file=-
```

**Deploy** (builds + pushes the image, then deploys to Cloud Run):

```bash
PROJECT_ID=<your-project-id> BUCKET=<your-bucket> ./scripts/deploy_cloud_run.sh
```

Then point `.firebaserc`'s `"default"` project at your project id, confirm
`firebase.json`'s rewrite `serviceId`/`region` match what you deployed, and:

```bash
firebase deploy --only hosting
```

**Verify:** `curl https://<hosting-domain>/health/live` → `200` (use this
endpoint, not `/healthz` — Google's frontend reserves the exact path
`/healthz` on Cloud Run's `*.run.app`-backed domains, including through a
Firebase Hosting rewrite, and returns its own 404 for it before the request
ever reaches the container; `/health/live`, `/metrics`, and everything
else are unaffected). Load the root URL and confirm the existing
token-paste `AuthGate` screen appears; after pasting the token, trigger
one on-demand run and confirm it survives a
redeploy (proves the GCS-backed `/data` volume actually persists across
instance churn, not just within one warm instance).

## The service loop

`PaperTradingService` (see `tradingagents/pro/service.py`) is the
composition root: snapshot source → full debate pipeline (recorded for the
dashboard) → execution router (validation → kill switch → circuit breaker
→ idempotent submit → audit) → bar-close position management →
`memory.close_trade`. Wire it in a small `main` per deployment; the demo
(`scripts/pro_dashboard_demo.py`) shows the pattern with fakes.

## Observability

- **Logs:** call `configure_structured_logging()` — one JSON object per
  line, extra fields via `logger.info(..., extra={"extra_fields": {...}})`.
- **Metrics:** `MetricsRegistry.render_prometheus()` — counters for runs,
  recommendations, rejections by stage, fills, closes; gauges for realized
  P&L and estimated LLM cost.
- **LLM cost:** wrap the model with `CostTrackingLLM` (stacks with the
  backtester's `CachingLLM`). Token counts are estimates (chars/4) until a
  pinned provider's usage metadata is wired.
- **Model pinning (AI-07):** set `models.require_pinned_models=True` in
  ProConfig for paper/live — `bundle_from_config` then refuses floating
  aliases (`gpt-5.5`) and demands dated snapshots (`gpt-5.5-2026-03-11`),
  so a provider-side model swap cannot change behavior without an eval
  rerun. Providers without dated aliases (DeepSeek) cannot satisfy this;
  leaving the flag off is an explicit acceptance of that drift risk.
- **Alerting (OBS-02):** pass an `AlertManager` to `PaperTradingService`
  — critical events (kill switch/breaker refusals, reconciliation drift,
  iteration errors, quarantined injections) fan out to sinks
  (`LogAlertSink`, `WebhookAlertSink` for Slack/PagerDuty bridges).
  Metric-level rules for Prometheus live in `deploy/prometheus-alerts.yml`.

## Operations

- **Kill switch:** `touch <data>/KILL` halts all new entries instantly (the
  switch is latching); reset requires an operator identity in code.
- **Circuit breaker:** trips on consecutive losses or daily-loss breach;
  daily component resets at day rollover, loss streaks do not.
- **Audit log:** hash-chained JSONL at `<data>/audit.jsonl`; verify with
  `AuditLog(path).verify()`. Ship it off-host for tamper resistance.
- **Reconciliation:** run `router.reconcile()` on a schedule; investigate
  any report with `in_sync == False` before allowing new entries.

## Paper → live promotion checklist (all are explicit sign-offs)

1. Paid/production data feeds approved and wired (docs/DATA_SOURCES.md).
2. A real venue transport implemented against `ExecutionAdapter` and
   soak-tested in paper mode (`LiveAdapterStub` refuses until replaced).
3. Venue credentials provisioned as secrets — never in the repo or image.
4. `ProConfig(mode=live, live_trading_enabled=True)` — the contract still
   forces `require_human_approval=True`.
5. A persistent LangGraph checkpointer configured (live builds refuse
   without one) and an operator workflow for answering the human-approval
   interrupt.
6. Kill switch path + circuit-breaker limits reviewed; audit shipping
   configured; reconciliation scheduled.
7. RL advisory (if used) retrained on production data and reviewed
   (ADR-0025).
8. Model IDs pinned to dated snapshots and `require_pinned_models=True`
   (AI-07); the eval suite rerun against exactly those snapshots.
9. A 30-day paper soak completed per docs/SOAK.md with its exit criteria
   met (OPS-04).

Until every box is ticked, the system will refuse live routing on its own.

## Live ops surfaces (go-live Phase 5)

- **Health**: `GET /health/live` aggregates feed health, venue
  reachability, clock skew, and run recency — 200 healthy, 503 degraded.
  Point an uptime monitor here; the hourly loop and the dead-man switch
  consume the same verdict.
- **Metrics**: `GET /metrics` (Prometheus text) now includes a
  `last_run_ts` heartbeat gauge alongside the existing counters.
- **Alerting**: set `PRO_TELEGRAM_BOT_TOKEN`/`PRO_TELEGRAM_CHAT_ID` and/or
  `PRO_ALERT_WEBHOOK_URL` (secrets layer in prod) — fills, disarms,
  reconciliation drift, degraded-feed-while-open, dead-man trips, and a
  daily P&L summary push out. Log + dashboard broadcast are always on.
- **Dead-man switch**: `PRO_DEADMAN_TIMEOUT_SECONDS` (default 600) — if
  health can't be confirmed for that long while live-armed, all resting
  orders are cancelled and the kill switch engages.
- Operator procedures live in docs/LIVE_TRADING_RUNBOOK.md.
