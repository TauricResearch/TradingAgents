# IIC-FORGE F4 — Exit-gate runbook

> Spec: [docs/superpowers/specs/2026-05-27-iic-forge-07-f4-orchestrator-design.md](../../docs/superpowers/specs/2026-05-27-iic-forge-07-f4-orchestrator-design.md) §9
> Evaluator: [scripts/f4_exit_gate.py](../../scripts/f4_exit_gate.py)

The F4 exit gate has two parts that pass independently:

1. **Synthetic-event smoke** — `pytest tests/smoke/test_f4_exit_gate.py` on the same commit. Must PASS.
2. **Live observation window** — 6–12 h with F3 adapters + F4 promoter+worker running on the dev machine. SLA `p95 ≤ 15 min` (or per the tiered rule when fewer than 3 briefs land).

## Pre-flight checklist

Run sequentially. Any failure → fix before proceeding.

1. **F3 stack healthy.**
   ```bash
   for svc in iic-sense-polygon iic-sense-rss iic-sense-gdelt iic-sense-macro \
              iic-sense-telegram iic-triage; do
       systemctl is-active "$svc" || { echo "❌ $svc not active"; exit 1; }
   done
   ```

2. **Watchlist non-empty.** The trigger rule requires `ticker ∈ watchlist`.
   ```bash
   /home/ziwei-huang/miniconda3/bin/python -m cli.main forge watchlist list
   ```
   If empty: `/home/ziwei-huang/miniconda3/bin/python -m cli.main forge watchlist add AAPL` (and the user's other standing tickers).

3. **Tickers reference table seeded.**
   ```bash
   sqlite3 /home/ziwei-huang/.tradingagents/iic.db "SELECT COUNT(*) FROM tickers WHERE active=1"
   # Expect ≥ 8000
   ```

4. **All cost guards confirmed OFF.** Gate observes the natural profile.
   ```bash
   /home/ziwei-huang/miniconda3/bin/python - <<'EOF'
   from tradingagents.default_config import DEFAULT_CONFIG as C
   for k in ("cost_guard_enabled", "trigger_backpressure_enabled",
             "trigger_daily_rate_enabled", "daily_budget_enabled"):
       assert C[k] is False, f"{k} must be False for the gate"
   print("all guards OFF ✓")
   EOF
   ```

5. **Synthetic smoke passes on the current commit.**
   ```bash
   cd /home/ziwei-huang/TradingAgents/TradingAgents
   /home/ziwei-huang/miniconda3/bin/python -m pytest tests/smoke/test_f4_exit_gate.py -v
   ```
   Must PASS.

6. **Disable unattended-upgrades for the window.**
   ```bash
   sudo systemctl stop unattended-upgrades.timer
   ```
   Re-enable after the gate completes.

7. **Promoter + worker units installed and enabled.**
   ```bash
   # The redis-server.service docker alias should already be installed from F3;
   # re-copy it here so a standalone F4 bring-up also satisfies the sensing/triage
   # Requires=redis-server.service dependency.
   sudo cp ops/systemd/redis-server.service \
           ops/systemd/iic-promoter.service ops/systemd/iic-worker.service \
           /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl start redis-server.service
   sudo systemctl enable --now iic-promoter iic-worker
   ```

## Run procedure

1. **Record `--since` timestamp.**
   ```bash
   export F4_GATE_SINCE=$(date -u +%Y-%m-%dT%H:%M:%SZ)
   echo "$F4_GATE_SINCE" > /tmp/f4_gate_since
   ```

2. **Hold sleep for the window.**
   ```bash
   systemd-inhibit --what=sleep --who="F4 exit gate" \
                   --why="12h orchestrator soak" sleep infinity &
   ```

3. **Walk away.** Recommended window: 12 h.

4. **At window end, run the evaluator.**
   ```bash
   F4_GATE_SINCE=$(cat /tmp/f4_gate_since)
   /home/ziwei-huang/miniconda3/bin/python scripts/f4_exit_gate.py --since "$F4_GATE_SINCE" --window-hours 12 \
       > docs/superpowers/artifacts/$(date -u +%Y-%m-%d)-f4-exit-gate-report.md
   ```

5. **Review the artifact.** Sign the operator line at the bottom.

6. **Re-enable unattended-upgrades and stop the inhibit:**
   ```bash
   sudo systemctl start unattended-upgrades.timer
   kill %1   # stop systemd-inhibit background job
   ```

## Pass criteria

Cited from spec §9:

- `NRestarts == 0` for `iic-promoter` and `iic-worker` over the window. (Restart audit in the artifact.)
- Synthetic-smoke result: PASS (recorded in the artifact alongside the live signal).
- Live SLA (tiered):
  - **≥ 3 briefs** during the window → `p95 latency ≤ 15 min`.
  - **1–2 briefs** → `max latency ≤ 15 min` + operator note confirming the window was "normal".
  - **0 briefs** → not a pass signal; re-run during a more active window.

## Failure modes and recovery

| Symptom | Likely cause | Fix |
|---|---|---|
| Promoter restarts > 0 | unhandled exception in the loop body | `journalctl -u iic-promoter` for traceback; the defensive `except Exception` should have swallowed it — file an issue |
| Worker restarts > 0 | OOM during persona fan-out, or an unhandled exception outside `drain_one`'s try/except | check `journalctl -u iic-worker` for `Killed (out of memory)`; raise `MemoryMax` if needed |
| Latency p95 > 15 min | personas slow, LLM upstream lag, queue backlog | check per-job timing in the artifact; consider falling back to `quick_think_llm` for the synthesis call (open question #2 in the spec) |
| 0 briefs during window | quiet news period or watchlist too small | spec §9 explicitly: re-run during an active window; do not pad with synthetic |
| `error` state jobs | LLM crash, malformed event, timeout | inspect `queue_jobs.error` via `/home/ziwei-huang/miniconda3/bin/python -m cli.main forge orchestrator status`; the underlying `runs` rows have artifacts under `data/runs/<run_id>/` |
