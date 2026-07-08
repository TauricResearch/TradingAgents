# OPS-04 — 30-Day Paper Soak Runbook

The soak is the last calendar-gated blocker before live promotion: 30
consecutive days of unattended paper trading with real data, real models,
and all safety rails armed. Nothing here is new machinery — it is the
production stack run for real, watched, and judged against exit criteria.

## What the soak proves

1. The loop survives real-world conditions unattended: feed outages,
   provider timeouts, weekend gaps, DST, restarts.
2. Safety rails fire for real reasons and never get bypassed: kill switch,
   circuit breaker, reconciliation gate, injection quarantine.
3. Cost and decision quality hold at production cadence, not just in evals.

## Start procedure

1. Pin models: dated snapshots + `models.require_pinned_models=True`
   (AI-07). Rerun the eval suite against exactly those snapshots and file
   the report next to this document.
2. Build and start the stack:

   ```bash
   docker build -f deploy/Dockerfile.pro -t tradingagents-pro:soak .
   PRO_DASHBOARD_TOKEN=<secret> docker compose -f deploy/docker-compose.pro.yml up -d
   ```

3. Wire alerting (OBS-02): a `WebhookAlertSink` pointed at a channel a
   human actually reads, plus Prometheus scraping the metrics endpoint
   with `deploy/prometheus-alerts.yml` loaded. Send a test alert and
   confirm a human saw it before day 1 counts.
4. Record the start: git SHA, image digest, model IDs, venue spec, risk
   limits, starting equity — in `docs/verification/soak_start.json`.
5. Verify durability: restart the container on day 1 and confirm
   rehydration (open positions reconstructed, reconcile in_sync).

## Daily checks (~5 minutes; automate what you can)

- Dashboard status strip: LIVE, no unexplained STALE windows; risk badge
  green unless a rail fired for a documented reason.
- Alert channel: every critical alert acknowledged and root-caused the
  same day. An unexplained critical alert **pauses the soak clock**.
- `iteration_errors_total` unchanged or explained (provider outage, feed
  gap); `reconciliation_failures_total` at zero (any drift is an incident).
- LLM spend: cumulative estimated cost within the agreed budget line.

## Weekly checks

- Rerun the eval suite (same pinned models); injection subset must stay
  at 100% resistance. A regression pauses the soak clock.
- Review the trade journal: every executed trade has evidence, a
  counterargument review, an invalidation condition, and exits that
  followed the plan (stop/ladder), not improvisation.
- Verify the audit chain: `AuditLog(path).verify()`; back it up off-host.
- Restart drill (week 2 and week 4): container restart mid-position;
  rehydration + reconcile must pass without manual fixes.

## Exit criteria (all must hold at day 30)

| # | Criterion |
|---|-----------|
| 1 | ≥ 30 consecutive days without an unexplained halt, crash, or drift |
| 2 | Zero reconciliation failures that required manual book repair |
| 3 | Every safety-rail activation root-caused (no bypasses, no resets without an operator identity) |
| 4 | Weekly evals green throughout, injection resistance 100% |
| 5 | Total LLM cost within budget; per-decision cost stable week over week |
| 6 | All positions explainable end-to-end from the dashboard alone |

Pausing the clock: incidents don't fail the soak, unexplained ones do.
A root-caused incident with a fix restarts the affected day; three
clock-pauses in a week mean restart the soak after remediation.

The soak result feeds checklist item 9 in docs/DEPLOYMENT.md. Sign-off is
a human decision recorded in DECISIONS.md — the system will keep refusing
live routing regardless until every promotion box is ticked.
