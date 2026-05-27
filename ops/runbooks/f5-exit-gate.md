# F5 Exit-Gate Runbook — 72-Hour Soak

Single contiguous 72-hour run against live F3 OSINT. Operator interacts
during the window to drive checks G4 / G5 / G6.

## Pre-flight checklist

- [ ] **Branch state.** On `feat/iic-forge-08-f5`, all 22 tasks committed,
      full test suite green: `pytest -v`.
- [ ] **Secrets.** `.env` contains:
        - `IIC_TELEGRAM_BOT_TOKEN=<your bot token>`
        - `IIC_SMTP_USER=<gmail address>`
        - `IIC_SMTP_APP_PASSWORD=<gmail app password>`
- [ ] **DEFAULT_CONFIG overrides** (env vars before starting soak):
        - `TRADINGAGENTS_TELEGRAM_BOT_ENABLED=1`
        - `TRADINGAGENTS_SMTP_ENABLED=1`
        - `TRADINGAGENTS_DASHBOARD_ENABLED=1`
        - `TRADINGAGENTS_DELIVERY_ENABLED_CHANNELS=telegram,email,cli`
        - `TRADINGAGENTS_ORCHESTRATOR_ENABLED=1` (from F4)
- [ ] **Test email** sent and received:
        `forge morning-digest now --dry-run` then manually inspect
        `data/briefs/<latest>.md`. Then full send (no `--dry-run`) and
        confirm receipt in Gmail.
- [ ] **Test Telegram** message: from any Telegram chat to the bot, send
      `/start`. Bot does not respond to commands (V1), but the connection
      should log `iic-telegram-bot polling started` in `journalctl -u iic-telegram-bot`.
- [ ] **Dashboard reachable**: `curl -fs http://127.0.0.1:8501/_stcore/health` returns 200.
- [ ] **F3 sensing** running and producing events:
        `sqlite3 data/iic.db "SELECT COUNT(*) FROM events WHERE ingested_ts > datetime('now', '-1 hour')"`
      returns >= 1.
- [ ] **F4 worker + promoter** running, queue depth = 0:
        `sqlite3 data/iic.db "SELECT state, COUNT(*) FROM queue_jobs GROUP BY state"`
- [ ] **systemd-inhibit** holding sleep off:
        `systemd-inhibit --what=sleep:idle --who=iic-soak --why="F5 72h soak" --mode=block sleep infinity &`

## Run procedure

1. **Mark start.** Record `SOAK_START=$(date -u +%Y-%m-%dT%H:%M:%SZ)`.
2. **Enable + start F5 units.**

   ```bash
   sudo cp ops/systemd/iic-*.service ops/systemd/iic-*.timer /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now iic-telegram-bot.service \
                                iic-action-handler.service \
                                iic-dashboard.service \
                                iic-morning.timer
   ```
3. **Hour 1 sanity check.**
   - Open dashboard at `http://127.0.0.1:8501`. All four tabs render
     (Briefs may be empty if no event_alerts yet).
   - Confirm `iic-telegram-bot` and `iic-action-handler` are `active (running)`.
4. **Drive G3 (deep-dive delivered).** Run on the soak host:
        `forge deepdive AAPL` and complete the interactive prompts —
        decline the backtest, decline refinement.
5. **Drive G4 (backtest prompt accepted → backtest completes).** When the
   next event_alert lands on Telegram, click **Run Backtest**. Within
   `tick_interval_seconds` (default 5s) the action moves to `done` with
   `result_backtest_id IS NOT NULL`. Verify on dashboard's Actions tab.
6. **Drive G5 (prompt expires).** Pick a subsequent event_alert and do
   NOT click. After `action_expires_hours=24h` (or temporarily lower the
   config to e.g. 1 hour just for one alert via env var override), the
   sweep marks it `expired`.
7. **Drive G6 (free-text refinement).** Reply to a Telegram event_alert
   message with text like "drop value, more conservative". Within ~1
   minute the refinement classifier runs, `compose_refinement` produces
   a child brief, and a refined alert lands as a follow-up Telegram message.

## Pass criteria

The evaluator script `scripts/f5_exit_gate.py` enforces criteria G1–G9.
Run it at `SOAK_START + 72h`:

```bash
python scripts/f5_exit_gate.py --since "$SOAK_START"
```

Output is `data/exit_gates/f5-<date>.md`. Pass = all 9 checks green.

## Failure modes and recovery

| Symptom | Likely cause | Recovery |
|---|---|---|
| Dashboard returns 502 | `iic-dashboard` crashed (Streamlit OOM) | `sudo systemctl restart iic-dashboard`; check journal for the OOM line |
| Telegram bot stops responding | Long-poll connection dropped | unit's `Restart=on-failure` handles it; offset persisted across restarts |
| Morning digest no-show | timer skipped due to clock change / suspend | Check `systemctl list-timers iic-morning.timer`; `Persistent=true` catches missed runs on next boot |
| SMTP send failures spike | Gmail rate-limited (>500/day) | unlikely at IIC volume; if it happens, reduce morning frequency or move to Mailgun |
| Refinement classifier produces gibberish JSON | quick_think_llm hallucinated | Safe-JSON regex catches it; classifier returns all-None overrides; action_handler logs warning and leaves action unprocessable |
| `action_handler` stuck in accept loop | RefinementDepthExceeded raised repeatedly | Operator inspects via dashboard; manually transitions action to `declined` |

## Cost outlook (per spec §13)

- 3 mornings × 20 tickers × 3 personas ≈ $7.20
- ~20 event alerts × 3 personas ≈ $2.40
- 1 deep-dive + 1 refinement ≈ $0.30
- 1 brief-scoped backtest ≈ $0.50
- F3 ingestion (~$0.05/day × 3) ≈ $0.15
- **Total estimate: ~$10.55**

Anomalies > 3× this estimate should pause the soak for investigation.
