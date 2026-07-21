---
id: 006
title: "Decide: run history and results persistence"
labels: [wayfinder:grilling]
status: closed
assignee: JMAN730
blocked-by: []
---

## Question

How does the web UI list and serve past runs?

- Reuse the existing results-dir layout the CLI writes (check `results_dir` in `tradingagents/default_config.py` and what `cli/main.py` saves per run) vs add a run-index (sqlite/json manifest)?
- Are CLI-produced runs and web-produced runs one shared history? (Recommended: yes — same results dir, web scans it; add a lightweight per-run manifest only if scanning proves insufficient.)
- What metadata does the history list need (ticker, date, decision, models used, duration)?

## Resolution

Decided from directly verified disk-layout facts (no skeptic pass — observable facts + policy).

Facts: CLI writes `{results_dir}/{TICKER}/{date}/reports/` (section .md files + `complete_report.md` via shared `write_report_tree`, tradingagents/reporting.py) plus `message_tool.log`; `_log_state` writes `{TICKER}/TradingAgentsStrategy_logs/full_states_log_{date}.json`; default `results_dir` = `~/.tradingagents/logs` (env-overridable, default_config.py:73). Normalized decision (BUY/SELL/HOLD), models used, and duration are persisted nowhere — `5_portfolio/decision.md` is prose; the memory log is a separate append-only markdown.

Decisions:
1. **One shared history.** Web scans the same `results_dir` tree the CLI writes; web runs write the identical report tree (ticket 005 already mandates incremental section writes mirroring the CLI). No separate web store.
2. **Per-run manifest, web runs only:** `{results_dir}/{TICKER}/{date}/run.json` — run_id, ticker, date, asset_type, status, decision (processed signal from `process_signal` post-phase), provider + deep/quick models, analysts selected, started/finished timestamps, duration, error summary when failed. Written because the history list's metadata (decision badges, models, duration in the prototype) is otherwise unrecoverable.
3. **Graceful degradation for CLI-era runs:** no run.json → list from dir names (ticker, date), decision shown as unknown, source tagged "cli". No best-effort prose parsing in v1.
4. **No sqlite index.** Two-level directory scan per `GET /api/runs`, in-process cache keyed on parent-dir mtimes. Localhost scale (hundreds of runs) makes an index premature; manifest-in-dir keeps the results tree the single source of truth and survives users deleting run dirs by hand.
5. **Report serving:** `GET /api/runs/{ticker}/{date}/report` returns the section markdown strings as JSON (7 sections mapping to `REPORT_SECTIONS`, cli/main.py:96-103, falling back to `complete_report.md`); client renders via the 004 pipeline. `full_states_log_*.json` and `message_tool.log` stay unexposed in v1 (debug artifacts).
