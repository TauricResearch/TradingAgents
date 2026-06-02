---
description: Run the heavy TradingAgents analysis for every ticker missing today's report (5-wide, auto-retry, then rebuild docs site)
argument-hint: "[CONCURRENCY=N] [TICKER ...]"
allowed-tools: Bash(bash .claude/run_missing_today.sh*), Bash(CONCURRENCY=* bash .claude/run_missing_today.sh*), Bash(TA_BUILD_SITE=* bash .claude/run_missing_today.sh*), Bash(TRADINGAGENTS_DATE=* bash .claude/run_missing_today.sh*)
---

Run `.claude/run_missing_today.sh` to analyze every ticker that does not yet
have a report for today. The script:

1. Discovers target tickers (the `docs/*/` folders, minus `stylesheets`) — or
   uses an explicit ticker list if given as arguments.
2. Skips any ticker that already has a `docs/<TICKER>/<YYYYMMDD>_*/` folder for
   today.
3. Pass 1: runs the missing tickers at `CONCURRENCY` (default **5** — verified
   safe; higher risks HTTP 429 rate limits on the API key).
4. Pass 2: re-runs any stragglers serially (429-safe).
5. Rebuilds the docs site (`build_reports_site.py` + `mkdocs build`) unless
   `TA_BUILD_SITE=0`.

Each run is a long, multi-agent heavy run — expect tens of minutes per ticker.
Launch it in the background so it survives the turn, then report what was
started and what (if anything) is still missing.

Arguments from the user (may be empty): $ARGUMENTS

Run exactly:

```bash
$ARGUMENTS bash .claude/run_missing_today.sh
```

If `$ARGUMENTS` contains bare ticker symbols (not `KEY=value` env prefixes),
pass them as positional args instead:

```bash
bash .claude/run_missing_today.sh $ARGUMENTS
```

Use `run_in_background: true`. After launching, give a one-line status: how
many tickers were missing and the background task id.
