# Live Trading Runbook

Operator procedures for the TradingAgents Pro live subsystem. Paper is the
default; nothing here trades real capital until you complete the arming
ceremony. When in doubt between convenience and safety, choose safety —
the system's most important feature is its ability to refuse to trade.

## Host requirement (read first)

**Do not run armed live on a laptop or Docker Desktop.** A sleep or lid
close leaves open positions unmanaged and the dead-man switch unable to
run. Target an always-on Linux host (small VPS or mini-PC) with NTP
running (venue signatures expire in 5 seconds — clock skew > 2s blocks
arming) and monitored uptime. Docker Desktop is fine for paper, shadow,
and canary rehearsal; the system logs a prominent warning and raises a
dashboard alert if it detects it is armed live on such a host.

## Preconditions (one-time)

1. Fund the venue account (start small). Create a **Trading-scope** API
   key — Delta India keys have no withdrawal scope by design. IP-whitelist
   it in the Delta dashboard.
2. Put keys in the secrets layer, not plaintext: `DELTA_API_KEY_FILE` /
   `DELTA_API_SECRET_FILE` (Docker secrets) or `sops exec-env`. Testnet
   keys (`DELTA_TESTNET_*`) may be plain env.
3. Set `PRO_DASHBOARD_TOKEN` (≥16 chars) — live mode refuses to boot
   without it. Optionally set `PRO_TELEGRAM_BOT_TOKEN` + `_CHAT_ID` so
   fills, disarms, drift, and the daily P&L reach your phone.
4. Copy `deploy/live.yaml.example` → `live.yaml` and fill in **every**
   risk limit deliberately (the loader refuses on any missing key).

## Arming ceremony

```
tradingagents-pro readiness-report            # every FAIL blocks arming
tradingagents-pro arm-live --config live.yaml --pair BTC-USD \
    --operator you --ttl-days 30              # testnet by default
```

`arm-live` runs the self-check, prints venue balance + configured limits +
worst-case daily loss, then requires you to type a generated confirmation
phrase. Arming is per-pair, expires after `--ttl-days` (default 30), and
is recorded in the hash-chained audit log. Confirm the amber
`LIVE — ARMED` banner in the dashboard header.

Promotion (shadow → canary → live) is never automatic: re-run the ceremony
at the new tier after reviewing `readiness-report` (Phase 6).

## Emergency Flatten

The one sanctioned dashboard→execution control, and its CLI twin. Both
cancel all resting orders, close all positions at market (reduce-only),
engage the kill switch, and disarm every pair — all audited.

- Dashboard: the red **EMERGENCY FLATTEN** button in the armed banner →
  type `FLATTEN`.
- CLI: `tradingagents-pro flatten --confirm` (or omit `--confirm` for the
  typed-phrase prompt).

Use it whenever you are unsure and cannot immediately diagnose.

## Incident response

- **Reconciliation drift** (book ≠ venue): the loop halts new entries and
  fires a critical alert. Investigate the audit log; once the truth is
  clear, `tradingagents-pro reconcile --accept-venue` adopts the venue
  book (audited). Do not resume until reconciled.
- **Loss-limit breach** (daily/weekly/drawdown): the monitor auto-cancels,
  flattens, and disarms. The breach latches across restarts — only
  re-running the arming ceremony clears it. Review what happened before
  re-arming.
- **Dead-man trip** (health unconfirmed for the timeout): all resting
  orders are cancelled and the kill switch engages. Fix the health cause
  (feed, venue, clock, wedged loop), then reset and re-arm.
- **Kill switch engaged**: `tradingagents-pro status` shows the reason.
  Resolve the cause; resetting the kill switch is a deliberate operator
  action, never automatic.

## Recovery from a crash / restart

Reconcile-on-boot is **mandatory and blocking**: on startup the OMS
replays its write-ahead journal and resolves every non-terminal order
against the venue before anything may trade (never-sent → abandoned;
missing-on-venue → rejected; open → adopted). If the venue is unreachable
during recovery, startup fails by design — a process that cannot account
for its orders does not trade.

After any restart, verify: `tradingagents-pro status` (arming + kill
switch), `/health/live` returns 200, the dashboard book matches the venue,
and `reconcile` reports in-sync. Loss-limit and arming state persist
across restarts on the `/data` volume.

## Health & monitoring

- `GET /health/live` — 200 healthy, 503 degraded (feeds, venue, clock,
  run recency). Point an uptime monitor at it.
- `GET /metrics` — Prometheus counters/gauges incl. `last_run_ts`;
  `deploy/prometheus-alerts.yml` has the alert rules.
- The daily P&L summary arrives once per UTC day on your alert channel.

## Staged rollout (Phase 6)

Arming tiers change where orders actually go:

- **shadow** — decisions run live; orders fill on the PAPER venue while
  the would-have-been live fill (crossing the real spread) is recorded to
  `shadow_fills.jsonl`. Zero capital at risk; divergence is measured.
- **canary** — orders go to the LIVE venue at the venue-minimum size,
  regardless of configured sizing. Proves the whole pipe with the
  smallest possible real order.
- **live** — live venue at configured sizing.

A pair armed canary/live while no live venue is wired is **refused**,
never silently paper-filled. `PRO_LIVE_VENUE=testnet|production` selects
the endpoint for the live route (testnet default).

Suggested promotion defaults (encode them in live.yaml `promotion:`):
≥ 28 days shadow, ≥ 14 days canary, zero unexplained reconciliation
incidents before sizing up. Check with:

```
tradingagents-pro readiness-report --config live.yaml
```

The report shows, per pair: current tier, decisions, gate-rejection
rate, shadow/canary durations, shadow-fill divergence, and any blockers.
Promotion is never automatic — re-run the arming ceremony at the new
tier.
