# F3 24h Exit-Gate Runbook

The F3 exit gate is **one contiguous 24-hour run** with **no process restarts
allowed**. A single `systemctl restart` of any sensing or triage unit during
the window invalidates the gate. Plan the start time around your day.

## Pre-flight checklist

Run through this list in order; do not skip. Each item is a `pass/fail` —
fix before continuing.

- [ ] Dev machine on AC power. Battery-only is not acceptable.
- [ ] `systemd-inhibit --what=sleep --who="F3 exit gate" --why="24h sensing soak" sleep infinity &` running.
- [ ] Screen lock disabled for the window (`gsettings set org.gnome.desktop.screensaver lock-enabled false`).
- [ ] Display sleep disabled (`gsettings set org.gnome.desktop.session idle-delay 0`).
- [ ] Unattended-upgrades disabled for the window (`sudo systemctl mask unattended-upgrades.service`). Re-enable after the gate.
- [ ] All six adapters' env vars set: POLYGON_API_KEY, TELEGRAM_API_ID/HASH/SESSION (sensing), X_BEARER_TOKEN (if enabling x), FRED_API_KEY, RSS_FEEDS, GDELT_QUERY.
- [ ] Telegram **sensing** session pre-authenticated: `/home/ziwei-huang/miniconda3/bin/python -m tradingagents.sensing.adapters.telegram` once, complete any 2FA prompts, Ctrl+C, then start under systemd.
- [ ] Redis running (`docker ps --filter name=iic-redis`), AOF on (`docker exec iic-redis redis-cli config get appendonly` → `yes`).
- [ ] `tickers` table seeded: `/home/ziwei-huang/miniconda3/bin/python -m cli.main forge sense reseed-tickers` → at least 8000 rows in `tickers` (or skip the gate and re-seed).
- [ ] Baseline watchlist set: `/home/ziwei-huang/miniconda3/bin/python -m cli.main forge watchlist add` for each of the user's standing tickers.
- [ ] **Pre-soak**: each adapter individually for 1 hour. Each must produce ≥1 event with `NRestarts=0`:
  ```bash
  for unit in iic-sense-{polygon,telegram,rss,gdelt,macro}; do
      sudo systemctl start "$unit.service"
      sleep 3600
      systemctl show "$unit.service" --property=NRestarts  # expect NRestarts=0
      sudo systemctl stop "$unit.service"
  done
  ```
- [ ] No pending reboot: `[ -f /var/run/reboot-required ] && echo NEEDS REBOOT || echo OK`.

## Start

```bash
START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "START=$START" | tee /tmp/f3-gate-start.txt

# Install the corrected units (includes the redis-server.service docker alias
# that the sensing/triage units now Require). This replaces any older
# iic-user units that pointed at /home/iic and /var/log/iic.
sudo cp ops/systemd/redis-server.service ops/systemd/iic-sense-*.service \
        ops/systemd/iic-triage.service ops/systemd/iic-watchlist-sweep.service \
        ops/systemd/iic-watchlist-sweep.timer /etc/systemd/system/
sudo systemctl daemon-reload

# Redis alias (starts the iic-redis docker container + blocks until it answers
# PING). The sensing/triage units pull this in via Requires=, but start it
# explicitly first so the readiness gate is satisfied up front.
sudo systemctl start redis-server.service

# Enable all systemd units.
sudo systemctl start \
  iic-sense-polygon iic-sense-telegram iic-sense-rss \
  iic-sense-gdelt iic-sense-macro \
  iic-triage iic-watchlist-sweep.timer

# x adapter is optional (per R-F3-3); enable only if X_BEARER_TOKEN works.
# sudo systemctl start iic-sense-x

# Confirm everything is "active (running)".
systemctl status iic-sense-* iic-triage
```

## During the run

- Do not touch any service unit. Do not run `systemctl restart`.
- Spot-check log volume every few hours: `journalctl -u 'iic-sense-*' -f`.
- If a service dies, the gate is invalidated. Note the time; the evaluator
  will flag it. Fix the root cause before re-attempting.

## Stop and evaluate

```bash
START=$(cat /tmp/f3-gate-start.txt | cut -d= -f2)
/home/ziwei-huang/miniconda3/bin/python scripts/f3_exit_gate.py --since "$START"
# Output: docs/superpowers/artifacts/2026-MM-DD-f3-exit-gate-report.md
```

Review the artifact:
- Auto criteria (events ≥100, no restarts, ≥1 auto-promoted watchlist row) must all be true.
- Spot-check the 30-row dedupe sample. Sign off in the artifact with **YES** or **NO**.

## Tear-down

```bash
sudo systemctl stop iic-sense-* iic-triage
sudo systemctl stop iic-watchlist-sweep.timer
sudo systemctl unmask unattended-upgrades.service
kill %1  # systemd-inhibit
```
