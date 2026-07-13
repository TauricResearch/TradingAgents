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
